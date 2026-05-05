import os
import re
import logging

from dataclasses import dataclass, field
from typing import ClassVar, List, Optional, Tuple

from django.db import transaction
from django.db.models import F, Max

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    TextSplitter,
)

from document.models import Document
from document_page.models import DocumentPage
from document_chunk.models import DocumentChunk
from document_chunk.services.chunk_bounding_polygon import ChunkBoundingPolygon
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
from document_chunk.services.exceptions.document_chunk_exceptions import (
    DocumentProcessingError,
    DocumentInvalidStatusError,
    DocumentPersistenceError,
    handle_persistence_errors,
)
from document_chunk.services.exceptions.embedding_exceptions import (
    EmbeddingError,
)
from document_chunk.services.pdf_text_extractor import PDFTextExtractor

logger = logging.getLogger(__name__)

__all__ = [
    "ArticleSplitter",
    "PageChunkProcessor",
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


def _doc_context_text(document: Document) -> str:
    filename = (
        os.path.basename(document.s3_key or "")
        .replace("_", " ")
        .replace("-", " ")
    )
    name = os.path.splitext(filename)[0].strip()
    return f"Documento legal: {name}" if name else "Documento legal"


class ArticleSplitter(TextSplitter):
    """
    Splits text on 'Artículo N.' / 'Articulo N.' boundaries so that each
    article becomes exactly one chunk, regardless of its length.

    Any content that appears before the first article (preamble, title, etc.)
    is returned as its own chunk so no text is lost.

    If an individual article exceeds ``max_tokens`` words (a fast proxy for
    token count), it is further subdivided by the fallback splitter to avoid
    overflowing the embedding model's context window.
    """

    _PATTERN = re.compile(r"(?=Art[ií]culo\s+\d+\.)", re.IGNORECASE)
    _MAX_TOKENS: int = 1000

    def __init__(self, max_tokens: int = _MAX_TOKENS, **kwargs):
        super().__init__(**kwargs)
        self._max_tokens = max_tokens
        self._fallback = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=self._max_tokens,
            chunk_overlap=0,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def split_text(self, text: str) -> List[str]:
        parts = self._PATTERN.split(text)
        chunks: List[str] = []

        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Use word count as a fast approximation of token count.
            if len(part.split()) > self._max_tokens:
                chunks.extend(self._fallback.split_text(part))
            else:
                chunks.append(part)

        return chunks


@dataclass(frozen=True)
class Chunk:
    """
    Immutable domain object representing a single text chunk produced by
    the chunking stage, including its resolved bounding polygons.

    Bounding polygons are resolved here (in the chunking worker) because
    the resolver requires sequential cursor state across all chunks — it
    cannot be parallelised across embedding workers.

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
    start_page: Optional[DocumentPage] = field(default=None)
    end_page: Optional[DocumentPage] = field(default=None)

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "chunk_index": self.chunk_index,
            "section_type": self.section_type,
            "section_title": self.section_title,
            "context_prefix": self.context_prefix,
            "bounding_polygons": self.bounding_polygons,
            "start_page": self.start_page,
            "end_page": self.end_page,
        }


@dataclass
class PageChunkProcessor:
    """
    Orchestrates the full processing pipeline for a single document page:
    text extraction, chunking, polygon resolution, persistence, and embedding.

    Responsibilities
    ----------------
    1. Extract text and word-level coordinates from the PDF stored in S3.
    2. Split the full document text into article-aware chunks via ArticleSplitter.
    3. Resolve bounding polygons for each chunk using sequential cursor state.
    4. Persist chunks to the database.
    5. Attach three embeddings per chunk (chunk / title / doc) via Bedrock Titan.
    6. Finalise the document status once all embeddings are processed.

    Document status transitions
    ---------------------------
    PROCESSING  — set on __post_init__ (work has started)
    PROCESSED   — set after finalisation if all chunk embeddings are present
    INCOMPLETED — set after finalisation if any chunk embeddings are null
    """

    CHUNK_BATCH_SIZE: ClassVar[int] = 5

    page: DocumentPage
    document: Document
    pdf_extractor: Optional[PDFTextExtractor] = field(default=None)
    splitter: Optional[TextSplitter] = field(default=None)
    bounding_polygon_resolver: Optional[ChunkBoundingPolygon] = field(
        default=None
    )
    embedding_processor: Optional[EmbeddingsProcessor] = field(default=None)
    chunk_batch_size: int = field(default=CHUNK_BATCH_SIZE)

    def __post_init__(self):
        if self.pdf_extractor is None:
            self.pdf_extractor = PDFTextExtractor()

        if self.splitter is None:
            self.splitter = ArticleSplitter()

        if self.bounding_polygon_resolver is None:
            self.bounding_polygon_resolver = ChunkBoundingPolygon()

        if self.embedding_processor is None:
            self.embedding_processor = EmbeddingsProcessor()

        self._update_document_status(Document.Status.PROCESSING)

    def process(self) -> List[Chunk]:
        """
        Run the full pipeline: extraction → chunking → persistence → embedding.

        Returns:
            The list of Chunk domain objects produced from the page.
        """
        logger.info("Processing document %s", self.document.id)

        pages = self.pdf_extractor.extract(
            os.environ["S3_BUCKET_NAME"],
            self.page.s3_key,
        )
        actual_page_number = self._page_number_from_key()
        for page_data in pages:
            page_data["page_number"] = actual_page_number

        chunks = self._text_to_chunks(pages)
        logger.info(
            "Generated %d chunks for document %s",
            len(chunks),
            self.document.id,
        )

        if not chunks:
            logger.info(
                "Page %s of document %s has no text, counting as processed",
                self.page.id,
                self.document.id,
            )
            self._finalize_document()
            return []

        db_chunks = self._persist_chunks(chunks)

        for db_chunk in db_chunks:
            self._attach_embeddings(db_chunk)

        self._finalize_document()

        return chunks

    def _persist_chunks(self, chunks: List[Chunk]) -> List[DocumentChunk]:
        """
        Persists chunks to the database and returns the created DB objects.

        Acquires a row-level lock on the document to prevent concurrent page
        processors from assigning duplicate chunk_index values (race condition
        on the unique_chunk_per_document constraint).
        """
        db_chunks = []
        with transaction.atomic():
            Document.objects.select_for_update().get(id=self.document.id)
            start_index = self._next_chunk_index()
            for local_offset, chunk in enumerate(chunks):
                global_index = start_index + local_offset
                try:
                    db_chunk = DocumentChunk.objects.create(
                        document_id=chunk.document_id,
                        content=chunk.content,
                        chunk_index=global_index,
                        section_type=chunk.section_type,
                        section_title=chunk.section_title,
                        context_prefix=chunk.context_prefix,
                        bounding_polygons=chunk.bounding_polygons,
                        start_page=chunk.start_page,
                        end_page=chunk.end_page,
                    )
                    db_chunks.append(db_chunk)
                except Exception as e:
                    logger.error(
                        "Failed to persist chunk %d for document %s: %s",
                        global_index,
                        chunk.document_id,
                        str(e),
                    )
                    raise DocumentPersistenceError(
                        f"Failed to persist chunk {global_index} "
                        f"for document {chunk.document_id}",
                        self.document,
                    ) from e
        return db_chunks

    def _attach_embeddings(self, chunk: DocumentChunk) -> None:
        """
        Generates three embeddings for the chunk and saves them.

        embedding       → "[section_type] section_title: content"
        embedding_title → "[section_type] section_title"
        embedding_doc   → "Documento legal: <filename>"

        Logs and leaves fields as None on any failure.
        """
        doc_text = _doc_context_text(self.document)
        chunk_text = (
            f"{chunk.context_prefix}: {chunk.content}"
            if chunk.context_prefix
            else chunk.content
        )
        title_text = chunk.context_prefix or chunk.content[:200]

        try:
            result = self.embedding_processor.embed_batch(
                [chunk_text, title_text, doc_text]
            )
            embeddings = result.embeddings
            chunk.embedding = embeddings[0]
            chunk.embedding_title = embeddings[1]
            chunk.embedding_doc = embeddings[2]
            chunk.save(
                update_fields=["embedding", "embedding_title", "embedding_doc"]
            )

            if result.has_errors():
                logger.warning(
                    "Embedding errors for chunk %s (document %s): %s",
                    chunk.id,
                    self.document.id,
                    result.errors,
                )
        except (EmbeddingError, RuntimeError, Exception) as e:
            logger.error(
                "Failed to embed chunk %s (document %s): %s",
                chunk.id,
                self.document.id,
                e,
            )

    def _finalize_document(self) -> None:
        """
        Atomically increments number_of_pages_processed and transitions
        document status to PROCESSED or INCOMPLETED once all pages are done.
        """
        with transaction.atomic():
            updated = Document.objects.filter(id=self.document.id).update(
                number_of_pages_processed=F("number_of_pages_processed") + 1
            )
            if not updated:
                logger.error(
                    "Document %s not found when finalising",
                    self.document.id,
                )
                return

            document = Document.objects.get(id=self.document.id)

            if document.number_of_pages is None:
                return

            if document.number_of_pages_processed < document.number_of_pages:
                return

            has_null = DocumentChunk.objects.filter(
                start_page__document=document, embedding__isnull=True
            ).exists()

            new_status = (
                Document.Status.INCOMPLETED
                if has_null
                else Document.Status.PROCESSED
            )
            Document.objects.filter(id=self.document.id).update(
                status=new_status
            )

            logger.info(
                "Document %s finalised with status %s (%d/%d pages done)",
                self.document.id,
                new_status,
                document.number_of_pages_processed,
                document.number_of_pages,
            )

    def _page_number_from_key(self) -> int:
        """
        Extracts the 1-based page number from the page's S3 key.

        Key format: pages/{document_id}/pages/page_{N}.pdf
        """
        filename = self.page.s3_key.rsplit("/", 1)[-1]  # "page_{N}.pdf"
        return int(filename.removeprefix("page_").removesuffix(".pdf"))

    def _next_chunk_index(self) -> int:
        result = DocumentChunk.objects.filter(
            document=self.document
        ).aggregate(Max("chunk_index"))
        max_index = result["chunk_index__max"]
        return (max_index + 1) if max_index is not None else 0

    def _text_to_chunks(self, pages_data: List[dict]) -> List[Chunk]:
        """
        Converts document text into Chunk objects with section context and
        resolved bounding polygons. Polygons are resolved in a single
        sequential pass to maintain correct cursor state across chunks.
        """
        full_text = "\n\n".join(page_data["text"] for page_data in pages_data)
        raw_chunks = self.splitter.split_text(full_text)

        chunks = []
        page_cursors: dict = {}

        for offset, text in enumerate(raw_chunks):
            section_type, section_title = _extract_section_context(text)
            context_prefix = f"[{section_type}] {section_title}"

            polygons, page_cursors = self.bounding_polygon_resolver.resolve(
                chunk_text=text,
                pages=pages_data,
                page_cursors=page_cursors,
            )
            bounding_polygons = [
                {"page_number": p.page_number, "points": p.points}
                for p in polygons
            ]

            logger.debug(
                "Chunk %d: section_type=%s, section_title=%s, "
                "context_prefix=%s, bounding_polygons=%s, content=%s",
                offset,
                section_type,
                section_title,
                context_prefix,
                bounding_polygons,
                text[:50] + "..." if len(text) > 50 else text,
            )

            chunks.append(
                Chunk(
                    content=text,
                    chunk_index=offset,
                    document_id=self.document.id,
                    section_type=section_type,
                    section_title=section_title,
                    context_prefix=context_prefix,
                    bounding_polygons=bounding_polygons,
                    start_page=self.page,
                    end_page=self.page,
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
