import os
import logging

from dataclasses import dataclass, field
from typing import ClassVar, Optional, List, Tuple

from document.models import Document
from document_chunk.models import DocumentChunk
from document_chunk.services.exceptions.document_chunk_exceptions import (
    DocumentProcessingError,
    DocumentInvalidStatusError,
    DocumentPersistenceError,
    handle_persistence_errors,
)
from document_chunk.services.pdf_text_extractor import PDFTextExtractor
from document_chunk.services.chunk_bounding_polygon import ChunkBoundingPolygon
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

    # Use the first non-empty line as the title; fall back to the first 200 chars.
    first_line = next(
        (ln.strip() for ln in text.splitlines() if ln.strip()), ""
    )
    section_title = (first_line or text)[:200]

    return section_type, section_title


@dataclass(frozen=True)
class Chunk:
    """
    Immutable domain object representing a single text chunk.

    Embeddings are not generated here — they are attached by the dedicated
    embedding worker after chunks are persisted.

    context_prefix  — the contextual header prepended when building the chunk
                      embedding: "[section_type] section_title"
    """

    content: str
    page_number: int
    document_id: int
    section_type: Optional[str] = field(default=None)
    section_title: Optional[str] = field(default=None)
    context_prefix: Optional[str] = field(default=None)
    embedding: Optional[list] = field(default=None, hash=False, compare=False)
    bounding_polygons: Optional[list] = field(
        default=None, hash=False, compare=False
    )

    def with_embedding(self, embedding: list) -> "Chunk":
        return Chunk(
            content=self.content,
            page_number=self.page_number,
            document_id=self.document_id,
            section_type=self.section_type,
            section_title=self.section_title,
            context_prefix=self.context_prefix,
            embedding=embedding,
            bounding_polygons=self.bounding_polygons,
        )


@dataclass
class DocumentChunkProcessor:
    """
    Orchestrates the text-extraction and chunking stage of the pipeline.

    Responsibilities
    ----------------
    1. Extract text and word-level coordinates from the PDF stored in S3.
    2. Split the full document text into context-aware chunks with bounding-polygon data.
    3. Persist all chunks to the database (all embeddings=None at this stage).
    4. Set document.embedding_batches_total so the embedding worker knows
       when the document is fully processed.

    Each chunk is enriched with:
    - section_type    — inferred section category (e.g. "Audiencia", "Sentencia")
    - section_title   — first meaningful line of the chunk
    - context_prefix  — "[section_type] section_title", used as the embedding header

    The embedding stage (three embeddings per chunk) is handled by the separate
    EmbeddingWorker, which consumes batches of chunk IDs from the embedding SQS queue.

    Document status transitions managed here
    -----------------------------------------
    PROCESSING  — set on __post_init__ (work has started)
    FAILED      — set if chunk persistence raises DocumentPersistenceError
    (PROCESSED / INCOMPLETED are set by ChunkEmbeddingService once all
     embedding batches have been counted.)
    """

    CHUNK_BATCH_SIZE: ClassVar[int] = 10

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

    def process(self) -> List[List[str]]:
        """
        Run the extraction and chunking stage.

        Returns:
            A list of batches, where each batch is a list of chunk ID
            strings (UUIDs). The caller (DocumentChunkingHandler) sends
            each batch as a separate SQS message to the embedding queue.
        Raises:
            DocumentPersistenceError: If saving chunks or updating status fails.
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

        try:
            saved_ids = self._save_chunks(chunks)
        except DocumentPersistenceError:
            self._update_document_status(Document.Status.FAILED)
            raise

        batches = [
            saved_ids[i: i + self.chunk_batch_size]
            for i in range(0, len(saved_ids), self.chunk_batch_size)
        ]

        # Record how many embedding batches will be dispatched so the
        # embedding worker can finalise the document status when the last
        # batch completes.
        total_batches = len(batches)
        self.document.embedding_batches_total = total_batches
        self.document.save(update_fields=["embedding_batches_total"])

        if total_batches == 0:
            # Edge case: document produced no chunks (e.g. empty PDF).
            self._update_document_status(Document.Status.PROCESSED)
            logger.info(
                "Document %s has no chunks, marked as PROCESSED",
                self.document.id,
            )

        logger.info(
            "Document %s: %d chunks saved, %d embedding batches to dispatch",
            self.document.id,
            len(saved_ids),
            total_batches,
        )

        return batches

    def _text_to_chunks(self, pages_data: List[dict]) -> List[Chunk]:
        """
        Converts document text into context-aware Chunk objects.

        Each chunk is annotated with section_type, section_title, and
        context_prefix so the embedding worker can generate targeted embeddings.
        """
        full_text = "\n\n".join(page["text"] for page in pages_data)
        raw_chunks = self.splitter.split_text(full_text)

        chunks = []
        page_cursors: dict = {}

        for text in raw_chunks:
            polygons, page_cursors = self.bounding_polygon_resolver.resolve(
                text, pages_data, page_cursors
            )

            page_number = (
                polygons[0].page_number
                if polygons
                else pages_data[0]["page_number"]
            )

            section_type, section_title = _extract_section_context(text)
            context_prefix = f"[{section_type}] {section_title}"

            chunks.append(
                Chunk(
                    content=text,
                    page_number=page_number,
                    document_id=self.document.id,
                    section_type=section_type,
                    section_title=section_title,
                    context_prefix=context_prefix,
                    bounding_polygons=[
                        {
                            "page_number": p.page_number,
                            "points": [list(pt) for pt in p.points],
                        }
                        for p in polygons
                    ],
                )
            )

        return chunks

    @handle_persistence_errors
    def _save_chunks(self, chunks: List[Chunk]) -> List[str]:
        """
        Persists all chunks to the database and returns their IDs.

        Chunks are saved without embeddings (all embedding fields = None).
        The embedding worker will populate these fields in a subsequent stage.

        Returns:
            List of chunk ID strings (UUIDs) in chunk_index order.
        Raises:
            DocumentPersistenceError: If bulk_create fails.
        """
        created = DocumentChunk.objects.bulk_create(
            [
                DocumentChunk(
                    document=self.document,
                    content=chunk.content,
                    section_type=chunk.section_type,
                    section_title=chunk.section_title,
                    context_prefix=chunk.context_prefix,
                    embedding=None,
                    embedding_title=None,
                    embedding_doc=None,
                    chunk_index=index,
                    bounding_polygons=chunk.bounding_polygons,
                )
                for index, chunk in enumerate(chunks)
            ]
        )

        logger.info(
            "Saved %d chunks for document %s",
            len(created),
            self.document.id,
        )

        return [str(c.id) for c in created]

    @handle_persistence_errors
    def _update_document_status(self, status: str) -> None:
        self.document.status = status
        self.document.save(update_fields=["status"])
        logger.info(
            "Updated document %s status to %s",
            self.document.id,
            status,
        )
