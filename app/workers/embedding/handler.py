import json
import logging

from workers.handler import Handler
from document_chunk.services.chunk_embedding_service import (
    ChunkEmbeddingService,
)

logger = logging.getLogger(__name__)


class EmbeddingHandler(Handler):
    """
    Consumes embedding-batch messages from SQS and, for each chunk in
    the batch: persists it, attaches embeddings, and resolves bounding
    polygons via ChunkEmbeddingService.

    Expected message body:
        {
            "document_id": "<uuid>",
            "chunks": [
                {
                    "content": "...",
                    "chunk_index": 0,
                    "section_type": "...",
                    "section_title": "...",
                    "context_prefix": "..."
                },
                ...
            ]
        }

    Failure handling
    ----------------
    Per-chunk errors (embedding or polygon) are handled inside
    ChunkEmbeddingService — affected fields are left as None and
    processing continues with the next chunk.
    The message is always deleted from SQS after the batch attempt.
    """

    def __init__(self):
        self.service = ChunkEmbeddingService()

    def handle(self, message: dict) -> None:
        body = json.loads(message["Body"])

        try:
            document_id = body["document_id"]
            chunks_data = body["chunks"]
        except KeyError as e:
            logger.error(
                "Malformed embedding batch message (missing field %s), "
                "message will be deleted: %s",
                e,
                message.get("MessageId"),
            )
            return

        if not isinstance(chunks_data, list) or not chunks_data:
            logger.error(
                "Embedding batch message has empty or invalid chunks, "
                "message will be deleted: %s",
                message.get("MessageId"),
            )
            return

        logger.info(
            "Processing embedding batch: document=%s, chunks=%d",
            document_id,
            len(chunks_data),
        )

        try:
            self.service.process_batch(document_id, chunks_data)
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
