import os
import logging

from dataclasses import dataclass, field
from typing import ClassVar, List, Optional, Tuple

from document.models import Document
from document_chunk.services.chunk_bounding_polygon import ChunkBoundingPolygon
from document_chunk.services.exceptions.document_chunk_exceptions import (
    DocumentProcessingError,
    DocumentInvalidStatusError,
    DocumentPersistenceError,
    handle_persistence_errors,
)
from document_chunk.services.pdf_text_extractor import PDFTextExtractor
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

__all__ = [
    "DocumentChunkProcessor",
    "DocumentProcessingError",
    "DocumentInvalidStatusError",
    "DocumentPersistenceError",
    "Chunk",
]

# Maps lowercase keywords found in chunk text to a canonical section type label.
_SECTION_KEYWORDS: List[Tuple[str, str]] = [
    ("audiencia", "Audiencia"),
    ("testimonio", "Testimonio"),
    ("testigo", "Testimonio"),
    ("sentencia", "Sentencia"),
    ("resolución", "Resolución"),
    ("resolucion", "Resolución"),
    ("apelación", "Apelación"),
    ("apelacion", "Apelación"),
    ("demanda", "Demanda"),
    ("demandante", "Demanda"),
    ("demandado", "Demanda"),
    ("contrato", "Contrato"),
    ("recurso", "Recurso"),
    ("providencia", "Providencia"),
    ("decreto", "Decreto"),
    ("auto", "Auto"),
    ("juzgado", "Juzgado"),
    ("tribunal", "Tribunal"),
    ("acuerdo", "Acuerdo"),
    ("denuncia", "Denuncia"),
    ("querella", "Querella"),
]


def _extract_section_context(text: str) -> Tuple[str, str]:
    """
    Infers a section type and title from the chunk text.

    Returns:
        (section_type, section_title)
        section_type  — canonical label (e.g. "Audiencia", "Sentencia")
        section_title — first meaningful line of the chunk (≤ 200 chars)
    """
    lower = text.lower()
    section_type = "Legal"
    for keyword, label in _SECTION_KEYWORDS:
        if keyword in lower:
            section_type = label
            break

    first_line = next(
        (ln.strip() for ln in text.splitlines() if ln.strip()), ""
    )
    section_title = (first_line or text)[:200]

    return section_type, section_title


@dataclass(frozen=True)
class Chunk:
    """
    Immutable domain object representing a single text chunk produced by
    the chunking stage, including its resolved bounding polygons.

    Bounding polygons are resolved here (in the chunking worker) because
    the resolver requires sequential cursor state across all chunks — it
    cannot be parallelised across embedding workers.

    The embedding worker receives chunks via SQS, persists them with the
    polygon data included, and attaches embeddings independently.

    context_prefix  — the contextual header prepended when building the chunk
                      embedding: "[section_type] section_title"
    chunk_index     — zero-based position in the document
    bounding_polygons — list of {"page_number": int, "points": [[x,y],...]}
    """

    content: str
    chunk_index: int
    document_id: int
    section_type: Optional[str] = field(default=None)
    section_title: Optional[str] = field(default=None)
    context_prefix: Optional[str] = field(default=None)
    bounding_polygons: Optional[list] = field(
        default=None, hash=False, compare=False
    )

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "chunk_index": self.chunk_index,
            "section_type": self.section_type,
            "section_title": self.section_title,
            "context_prefix": self.context_prefix,
            "bounding_polygons": self.bounding_polygons,
        }


@dataclass
class DocumentChunkProcessor:
    """
    Orchestrates the text-extraction, chunking, and polygon-resolution stage.

    Responsibilities
    ----------------
    1. Extract text and word-level coordinates from the PDF stored in S3.
    2. Split the full document text into context-aware chunks.
    3. Resolve bounding polygons for each chunk using sequential cursor state.
    4. Return chunks grouped in batches ready for the embedding queue.

    Polygon resolution must happen here because it requires a single sequential
    pass over all chunks in order — it cannot be split across parallel workers.

    The embedding worker only needs to persist chunks and attach embeddings.

    Document status transitions managed here
    -----------------------------------------
    PROCESSING  — set on __post_init__ (work has started)
    PROCESSED   — set immediately when the document produces no chunks
    (PROCESSED / INCOMPLETED are set by ChunkEmbeddingService once all
     embedding batches have been counted for non-empty documents.)
    """

    CHUNK_BATCH_SIZE: ClassVar[int] = 5

    document: Document
    pdf_extractor: Optional[PDFTextExtractor] = field(default=None)
    splitter: Optional[RecursiveCharacterTextSplitter] = field(default=None)
    bounding_polygon_resolver: Optional[ChunkBoundingPolygon] = field(
        default=None
    )
    chunk_batch_size: int = field(default=CHUNK_BATCH_SIZE)

    def __post_init__(self):
        if self.pdf_extractor is None:
            self.pdf_extractor = PDFTextExtractor()

        if self.splitter is None:
            self.splitter = (
                RecursiveCharacterTextSplitter.from_tiktoken_encoder(
                    encoding_name="cl100k_base",
                    chunk_size=500,
                    chunk_overlap=50,
                    separators=["\n\n", "\n", ". ", " ", ""],
                )
            )

        if self.bounding_polygon_resolver is None:
            self.bounding_polygon_resolver = ChunkBoundingPolygon()

        self._update_document_status(Document.Status.PROCESSING)

    def process(self) -> List[List[Chunk]]:
        """
        Run the extraction, chunking, and polygon-resolution stage.

        Returns:
            A list of batches, each containing up to CHUNK_BATCH_SIZE Chunk
            objects with bounding_polygons already resolved.
        """
        logger.info("Processing document %s", self.document.id)

        pages = self.pdf_extractor.extract(
            os.environ["S3_BUCKET_NAME"],
            self.document.s3_key,
        )
        chunks = self._text_to_chunks(pages)

        logger.info(
            "Generated %d chunks for document %s",
            len(chunks),
            self.document.id,
        )

        batches = [
            chunks[i: i + self.chunk_batch_size]
            for i in range(0, len(chunks), self.chunk_batch_size)
        ]

        if not batches:
            self._update_document_status(Document.Status.PROCESSED)
            logger.info(
                "Document %s has no chunks, marked as PROCESSED",
                self.document.id,
            )
            return []

        logger.info(
            "Document %s: %d chunks in %d batches to dispatch",
            self.document.id,
            len(chunks),
            len(batches),
        )

        return batches

    def _text_to_chunks(self, pages_data: List[dict]) -> List[Chunk]:
        """
        Converts document text into Chunk objects with section context and
        resolved bounding polygons. Polygons are resolved in a single
        sequential pass to maintain correct cursor state across chunks.
        """
        full_text = "\n\n".join(page["text"] for page in pages_data)
        raw_chunks = self.splitter.split_text(full_text)

        chunks = []
        page_cursors: dict = {}

        for index, text in enumerate(raw_chunks):
            section_type, section_title = _extract_section_context(text)
            context_prefix = f"[{section_type}] {section_title}"

            try:
                resolved, page_cursors = (
                    self.bounding_polygon_resolver.resolve(
                        text, pages_data, page_cursors
                    )
                )
                bounding_polygons = [
                    {
                        "page_number": p.page_number,
                        "points": [list(pt) for pt in p.points],
                    }
                    for p in resolved
                ]
            except Exception as e:
                logger.error(
                    "Failed to resolve polygons for chunk %d of document %s: %s",
                    index,
                    self.document.id,
                    e,
                )
                bounding_polygons = None

            chunks.append(
                Chunk(
                    content=text,
                    chunk_index=index,
                    document_id=self.document.id,
                    section_type=section_type,
                    section_title=section_title,
                    context_prefix=context_prefix,
                    bounding_polygons=bounding_polygons,
                )
            )

        return chunks

    @handle_persistence_errors
    def _update_document_status(self, status: str) -> None:
        self.document.status = status
        self.document.save(update_fields=["status"])
        logger.info(
            "Updated document %s status to %s",
            self.document.id,
            status,
        )
