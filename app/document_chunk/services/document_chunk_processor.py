import os
import logging

from dataclasses import dataclass, field
from typing import ClassVar, Optional, List

from document.models import Document
from document_chunk.models import DocumentChunk
from document_chunk.services.exceptions.embedding_exceptions import (
    EmbeddingError,
    EmbeddingValidationError,
)
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
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


@dataclass(frozen=True)
class Chunk:
    """
    Immutable domain object. An embedding-enriched version is produced
    via Chunk.with_embedding() rather than mutating the instance.
    """

    content: str
    page_number: int
    document_id: int
    embedding: Optional[list] = field(default=None, hash=False, compare=False)

    def with_embedding(self, embedding: list) -> "Chunk":
        """
        Return a new Chunk with the embedding attached.
        Args:
            embedding: The embedding to attach to the chunk.
        Returns:
            A new Chunk instance with the embedding attached.
        """
        return Chunk(
            content=self.content,
            page_number=self.page_number,
            document_id=self.document_id,
            embedding=embedding,
        )


@dataclass
class DocumentChunkProcessor:
    """
    Orchestrates the full document processing pipeline: text extraction,
    chunking, embedding generation, and persistence.

    Only processes documents whose status is CREATED. Raises
    DocumentInvalidStatusError immediately if the document is in any
    other status.

    Text extraction is delegated to PDFTextExtractor, keeping this class
    focused on chunking, embeddings, and document state management.

    Embeddings are generated in batches of `embedding_batch_size`. If a
    batch fails, the affected chunks are saved without an embedding and the
    document is marked as INCOMPLETED, allowing the caller to retry only
    the chunks that are missing embeddings. If all batches succeed, the
    document is marked as PROCESSED.
    """

    EMBEDDING_BATCH_SIZE: ClassVar[int] = 100

    document: Document
    pdf_extractor: Optional[PDFTextExtractor] = field(default=None)
    embedding_processor: Optional[EmbeddingsProcessor] = field(default=None)
    splitter: Optional[RecursiveCharacterTextSplitter] = field(default=None)
    embedding_batch_size: int = field(default=EMBEDDING_BATCH_SIZE)

    def __post_init__(self):
        if self.pdf_extractor is None:
            self.pdf_extractor = PDFTextExtractor()

        if self.embedding_processor is None:
            self.embedding_processor = EmbeddingsProcessor()

        if self.splitter is None:
            self.splitter = (
                RecursiveCharacterTextSplitter.from_tiktoken_encoder(
                    encoding_name="cl100k_base",
                    chunk_size=500,
                    chunk_overlap=50,
                    separators=["\n\n", "\n", ". ", " ", ""],
                )
            )

        self._update_document_status(Document.Status.PROCESSING)

    def process(self) -> List[Chunk]:
        """
        Run the full processing pipeline for the document.

        Only processes documents in CREATED status.

        Returns:
            A list of Chunk instances, each with an embedding if generation
            succeeded, or embedding=None if its batch failed.
        Raises:
            DocumentInvalidStatusError: If the document is not in CREATED status.
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

        chunks = self._attach_embeddings_in_batches(chunks)

        failed_count = sum(1 for c in chunks if c.embedding is None)

        try:
            self._save_chunks(chunks)
        except DocumentPersistenceError:
            self._update_document_status(Document.Status.FAILED)
            raise

        if failed_count:
            logger.warning(
                "Document %s saved with %d chunks missing embeddings",
                self.document.id,
                failed_count,
            )
            self._update_document_status(Document.Status.INCOMPLETED)
        else:
            logger.info(
                "Embedding generation completed for document %s",
                self.document.id,
            )
            self._update_document_status(Document.Status.PROCESSED)

        return chunks

    def _text_to_chunks(self, pages_data: List[dict]) -> List[Chunk]:
        """
        Converts page text into chunks using the configured text splitter.
        Args:
            pages_data: A list of dicts containing 'page_number' and 'text'.
        Returns:
            A list of Chunk objects.
        """
        chunks = []

        for page in pages_data:
            for text in self.splitter.split_text(page["text"]):
                chunks.append(
                    Chunk(
                        content=text,
                        page_number=page["page_number"],
                        document_id=self.document.id,
                    )
                )

        return chunks

    def _attach_embeddings_in_batches(
        self, chunks: List[Chunk]
    ) -> List[Chunk]:
        """
        Attaches embeddings to chunks in batches of `embedding_batch_size`.

        Each batch is processed independently. If a batch fails, those chunks
        are left with embedding=None and processing continues with the next
        batch.
        Args:
            chunks: A list of Chunk objects to attach embeddings to.
        Returns:
            A list of Chunk objects. Chunks whose batch succeeded carry their
            embedding; chunks whose batch failed retain embedding=None.
        """
        result = []

        for batch_start in range(0, len(chunks), self.embedding_batch_size):
            batch = chunks[
                batch_start: batch_start + self.embedding_batch_size
            ]
            result.extend(self._attach_embeddings(batch))

        return result

    def _attach_embeddings(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        Attempts to attach embeddings to a single batch of chunks via one
        API call. If the call fails, the chunks are returned unchanged
        (embedding=None) and the error is logged.
        Args:
            chunks: A list of Chunk objects representing one batch.
        Returns:
            A list of Chunk objects with embeddings attached if the call
            succeeded, or unchanged if it failed.
        """
        try:
            texts = [c.content for c in chunks]

            embedding_result = self.embedding_processor.embed_batch(texts)
            embedding_result.raise_on_errors()

            return [
                chunk.with_embedding(emb)
                for chunk, emb in zip(chunks, embedding_result.embeddings)
            ]

        except (EmbeddingError, EmbeddingValidationError, RuntimeError) as e:
            logger.error(
                "Embedding batch failed for document %s (%d chunks skipped): %s",
                self.document.id,
                len(chunks),
                e,
            )
            return chunks

    @handle_persistence_errors
    def _save_chunks(self, chunks: List[Chunk]) -> None:
        """
        Persists all chunks to the database in a single bulk operation.
        Chunks may have embedding=None if their batch failed during
        embedding generation.
        Args:
            chunks: A list of Chunk objects, with or without embeddings.
        Raises:
            DocumentPersistenceError: If saving fails.
        """
        DocumentChunk.objects.bulk_create(
            [
                DocumentChunk(
                    document=self.document,
                    content=chunk.content,
                    embedding=chunk.embedding,
                    chunk_index=index,
                )
                for index, chunk in enumerate(chunks)
            ]
        )

        logger.info(
            "Saved %d chunks for document %s",
            len(chunks),
            self.document.id,
        )

    @handle_persistence_errors
    def _update_document_status(self, status: str) -> None:
        """
        Updates the status of the document being processed.
        Args:
            status: The new status to set on the document.
        Raises:
            DocumentPersistenceError: If the document status cannot be updated.
        """
        self.document.status = status
        self.document.save(update_fields=["status"])
        logger.info(
            "Updated document %s status to %s",
            self.document.id,
            status,
        )
