import logging
import os

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

_EMBED_FIELDS = ["embedding", "embedding_title", "embedding_doc"]


def _doc_context_text(document: Document) -> str:
    """Builds a document-level description string used for embedding_doc."""
    filename = (
        os.path.basename(document.s3_key or "")
        .replace("_", " ")
        .replace("-", " ")
    )
    name = os.path.splitext(filename)[0].strip()
    return f"Documento legal: {name}" if name else "Documento legal"


class ChunkEmbeddingService:
    """
    Processes a single embedding batch: fetches the given chunks, generates
    three embeddings per chunk (chunk, title, doc), persists the results, and
    advances the per-document batch counter so the document status can be
    finalised once every batch has been processed.

    Embedding strategy per chunk
    ----------------------------
    embedding       → "[section_type] section_title: content"  (full contextual chunk)
    embedding_title → "[section_type] section_title"           (section header only)
    embedding_doc   → "Documento legal: <filename>"            (document identifier)

    Failure handling
    ----------------
    Individual embedding failures leave the affected field as None.
    The batch is still counted as *done* so the document status is finalised
    correctly even when some embeddings fail.
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

        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            logger.error(
                "Document %s not found — skipping embedding batch", document_id
            )
            self._finalize_document(document_id)
            return

        self._embed_and_update(chunks, document, document_id)
        self._finalize_document(document_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _embed_and_update(
        self, chunks: list, document: Document, document_id: str
    ) -> None:
        """
        Generates three embeddings per chunk in a single batched API call and
        bulk-updates the chunks.  Individual failures leave the field as None.
        """
        n = len(chunks)
        doc_text = _doc_context_text(document)

        # Build three text lists (chunk / title / doc) and flatten into one batch.
        chunk_texts = [
            (
                f"{c.context_prefix}: {c.content}"
                if c.context_prefix
                else c.content
            )
            for c in chunks
        ]
        title_texts = [c.context_prefix or c.content[:200] for c in chunks]
        doc_texts = [doc_text] * n

        all_texts = chunk_texts + title_texts + doc_texts

        try:
            result = self.embedding_processor.embed_batch(all_texts)
        except (EmbeddingError, EmbeddingValidationError, RuntimeError) as e:
            logger.error(
                "Embedding batch failed for document %s "
                "(%d chunks, embeddings left null): %s",
                document_id,
                n,
                e,
            )
            return

        embeddings = (
            result.embeddings
        )  # List[Optional[List[float]]], length = 3*n

        for i, chunk in enumerate(chunks):
            chunk.embedding = embeddings[i]
            chunk.embedding_title = embeddings[n + i]
            chunk.embedding_doc = embeddings[2 * n + i]

        DocumentChunk.objects.bulk_update(chunks, _EMBED_FIELDS)

        success = sum(1 for e in embeddings[:n] if e is not None)
        logger.info(
            "Embedded %d/%d chunks for document %s",
            success,
            n,
            document_id,
        )

        if result.has_errors():
            logger.warning(
                "Embedding batch for document %s had %d error(s): %s",
                document_id,
                len(result.errors),
                result.errors,
            )

    def _finalize_document(self, document_id: str) -> None:
        """
        Atomically increments embedding_batches_done. When the counter
        reaches embedding_batches_total the document status is set to
        PROCESSED (all chunk embeddings present) or INCOMPLETED (some null).
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
                "Document %s finalised with status %s (%d/%d batches done)",
                document_id,
                new_status,
                document.embedding_batches_done,
                document.embedding_batches_total,
            )
