import logging

from django.db import transaction
from django.db.models import F

from document.models import Document
from document_chunk.models import DocumentChunk
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
from document_chunk.services.exceptions.embedding_exceptions import (
    EmbeddingError,
    EmbeddingValidationError,
)

logger = logging.getLogger(__name__)

__all__ = ["ChunkEmbeddingService"]


class ChunkEmbeddingService:
    """
    Processes a single embedding batch: fetches the given chunks, requests
    embeddings from Bedrock, persists the results, and advances the
    per-document batch counter so the document status can be finalised once
    every batch has been processed.

    Failure handling
    ----------------
    If the Bedrock call fails the affected chunks keep embedding=None and
    the error is logged. The batch is still counted as *done* so the
    document status is finalised correctly even when some batches fail.
    """

    def __init__(self, embedding_processor: EmbeddingsProcessor = None):
        self.embedding_processor = embedding_processor or EmbeddingsProcessor()

    def process_batch(self, document_id: str, chunk_ids: list) -> None:
        """
        Embed the given chunks and persist the result.

        Args:
            document_id: UUID (str) of the parent document.
            chunk_ids:   List of DocumentChunk UUID strings to embed.
        """
        chunks = list(
            DocumentChunk.objects.filter(
                id__in=chunk_ids,
                document_id=document_id,
            )
        )

        if not chunks:
            logger.warning(
                "No chunks found for document %s with ids %s — skipping batch",
                document_id,
                chunk_ids,
            )
            self._finalize_document(document_id)
            return

        self._embed_and_update(chunks, document_id)
        self._finalize_document(document_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _embed_and_update(self, chunks: list, document_id: str) -> None:
        """
        Calls the embedding API for the batch and bulk-updates the chunks.
        On any failure the chunks are left with embedding=None and the
        error is logged — no exception is re-raised.
        """
        try:
            texts = [c.content for c in chunks]
            result = self.embedding_processor.embed_batch(texts)
            result.raise_on_errors()

            for chunk, embedding in zip(chunks, result.embeddings):
                chunk.embedding = embedding

            DocumentChunk.objects.bulk_update(chunks, ["embedding"])

            logger.info(
                "Embedded %d chunks for document %s",
                len(chunks),
                document_id,
            )

        except (EmbeddingError, EmbeddingValidationError, RuntimeError) as e:
            logger.error(
                "Embedding batch failed %s (%d chunks, embeddings left null): %s",
                document_id,
                len(chunks),
                e,
            )

    def _finalize_document(self, document_id: str) -> None:
        """
        Atomically increments embedding_batches_done. When the counter
        reaches embedding_batches_total the document status is set to
        PROCESSED (all embeddings present) or INCOMPLETED (some null).
        """
        with transaction.atomic():
            updated = Document.objects.filter(id=document_id).update(
                embedding_batches_done=F("embedding_batches_done") + 1
            )
            if not updated:
                logger.error(
                    "Document %s not found when finalising embedding batch",
                    document_id,
                )
                return

            document = Document.objects.get(id=document_id)

            if document.embedding_batches_total is None:
                return

            if (
                document.embedding_batches_done
                < document.embedding_batches_total
            ):
                return

            has_null = DocumentChunk.objects.filter(
                document=document, embedding__isnull=True
            ).exists()

            new_status = (
                Document.Status.INCOMPLETED
                if has_null
                else Document.Status.PROCESSED
            )
            Document.objects.filter(id=document_id).update(status=new_status)

            logger.info(
                "Document %s finalised with status %s " "(%d/%d batches done)",
                document_id,
                new_status,
                document.embedding_batches_done,
                document.embedding_batches_total,
            )
