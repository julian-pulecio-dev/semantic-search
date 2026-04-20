import logging
import os

from django.db import transaction
from django.db.models import F
from typing import Optional

from document.models import Document
from document_chunk.models import DocumentChunk
from document_page.models import DocumentPage
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
from document_chunk.services.exceptions.embedding_exceptions import (
    EmbeddingError,
    EmbeddingValidationError,
)

logger = logging.getLogger(__name__)

__all__ = ["ChunkEmbeddingService"]


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
    Processes a single embedding batch received from SQS.

    For each chunk in the batch:
      1. Create a DocumentPage to group the batch.
      2. Persist the chunk (content, metadata, bounding_polygons from message).
      3. Attach three embeddings (chunk / title / doc). On failure, logs the
         error and leaves the embedding fields as None.

    After all chunks have been processed, advances the per-document page
    counter so the document status can be finalised once every batch is done.

    Embedding strategy per chunk
    ----------------------------
    embedding       → "[section_type] section_title: content"  (full contextual chunk)
    embedding_title → "[section_type] section_title"           (section header only)
    embedding_doc   → "Documento legal: <filename>"            (document identifier)
    """

    def __init__(self, embedding_processor: EmbeddingsProcessor = None):
        self.embedding_processor = embedding_processor or EmbeddingsProcessor()

    def process_batch(self, document_id: str, chunks_data: list) -> None:
        """
        Persist and embed the given chunk data dicts.

        Args:
            document_id:  UUID (str) of the parent document.
            chunks_data:  List of chunk dicts, each with keys:
                          content, chunk_index, section_type, section_title,
                          context_prefix, bounding_polygons.
        """
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            logger.error(
                "Document %s not found — skipping embedding batch", document_id
            )
            return

        page = DocumentPage.objects.create(
            document=document,
            number_of_chunks=len(chunks_data),
        )

        for chunk_data in chunks_data:
            db_chunk = self._persist_chunk(page, chunk_data)
            if db_chunk is None:
                continue
            self._attach_embeddings(db_chunk, document)

        self._finalize_document(document_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _persist_chunk(
        self, page: DocumentPage, chunk_data: dict
    ) -> Optional[DocumentChunk]:
        """Creates and saves a DocumentChunk with polygon data but no embeddings."""
        try:
            return DocumentChunk.objects.create(
                page=page,
                content=chunk_data["content"],
                chunk_index=chunk_data["chunk_index"],
                section_type=chunk_data.get("section_type"),
                section_title=chunk_data.get("section_title"),
                context_prefix=chunk_data.get("context_prefix"),
                bounding_polygons=chunk_data.get("bounding_polygons"),
            )
        except Exception as e:
            logger.error(
                "Failed to persist chunk index=%s for document %s: %s",
                chunk_data.get("chunk_index"),
                page.document_id,
                e,
            )
            return None

    def _attach_embeddings(
        self, chunk: DocumentChunk, document: Document
    ) -> None:
        """
        Generates three embeddings for the chunk and saves them.
        Logs and leaves fields as None on any failure.
        """
        doc_text = _doc_context_text(document)
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
                    document.id,
                    result.errors,
                )
        except (
            EmbeddingError,
            EmbeddingValidationError,
            RuntimeError,
            Exception,
        ) as e:
            logger.error(
                "Failed to embed chunk %s (document %s): %s",
                chunk.id,
                document.id,
                e,
            )

    def _finalize_document(self, document_id: str) -> None:
        """
        Atomically increments number_of_pages_processed. When the counter
        reaches number_of_pages the document status is set to
        PROCESSED (all chunk embeddings present) or INCOMPLETED (some null).
        """
        with transaction.atomic():
            updated = Document.objects.filter(id=document_id).update(
                number_of_pages_processed=F("number_of_pages_processed") + 1
            )
            if not updated:
                logger.error(
                    "Document %s not found when finalising embedding batch",
                    document_id,
                )
                return

            document = Document.objects.get(id=document_id)

            if document.number_of_pages is None:
                return

            if (
                document.number_of_pages_processed
                < document.number_of_pages
            ):
                return

            has_null = DocumentChunk.objects.filter(
                page__document=document, embedding__isnull=True
            ).exists()

            new_status = (
                Document.Status.INCOMPLETED
                if has_null
                else Document.Status.PROCESSED
            )
            Document.objects.filter(id=document_id).update(status=new_status)

            logger.info(
                "Document %s finalised with status %s (%d/%d pages done)",
                document_id,
                new_status,
                document.number_of_pages_processed,
                document.number_of_pages,
            )
