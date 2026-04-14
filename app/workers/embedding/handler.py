import json
import logging

from workers.handler import Handler
from document_chunk.services.chunk_embedding_service import (
    ChunkEmbeddingService,
)

logger = logging.getLogger(__name__)


class EmbeddingHandler(Handler):
    """
    Consumes embedding-batch messages from SQS and attaches embeddings to
    the referenced chunks via ChunkEmbeddingService.

    Expected message body:
        {"document_id": "<uuid>", "chunk_ids": ["<uuid>", ...]}

    Failure handling
    ----------------
    If the embedding call fails, ChunkEmbeddingService logs the error and
    leaves the affected chunks with embedding=None. The batch is still
    counted as done so the document status is finalised correctly.
    No exception is re-raised from handle() — the message is deleted from
    SQS after every attempt (success or graceful failure).
    """

    def __init__(self):
        self.service = ChunkEmbeddingService()

    def handle(self, message: dict) -> None:
        body = json.loads(message["Body"])

        try:
            document_id = body["document_id"]
            chunk_ids = body["chunk_ids"]
        except KeyError as e:
            logger.error(
                "Malformed embedding batch message (missing field %s), "
                "message will be deleted: %s",
                e,
                message.get("MessageId"),
            )
            return

        if not isinstance(chunk_ids, list) or not chunk_ids:
            logger.error(
                "Embedding batch message has empty or invalid chunk_ids, "
                "message will be deleted: %s",
                message.get("MessageId"),
            )
            return

        logger.info(
            "Processing embedding batch: document=%s, chunks=%d",
            document_id,
            len(chunk_ids),
        )

        try:
            self.service.process_batch(document_id, chunk_ids)
        except Exception:
            logger.exception(
                "Unhandled exception in process_batch for document=%s, "
                "message will be deleted",
                document_id,
            )

    def on_success(self, message: dict) -> None:
        logger.info("Embedding batch message processed successfully")

    def on_error(self, message: dict, exception: Exception) -> None:
        logger.error(
            "Unexpected error in embedding handler for message=%s",
            message.get("MessageId", "unknown"),
            exc_info=exception,
        )

    def cleanup(self) -> None:
        pass
