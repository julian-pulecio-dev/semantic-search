import json
import logging
import os
import boto3

from workers.handler import Handler
from document.models import Document
from document_chunk.services.document_chunk_processor import (
    DocumentChunkProcessor,
    DocumentProcessingError,
)

logger = logging.getLogger(__name__)


class DocumentChunkingHandler(Handler):
    """
    Consumes S3-upload events from SQS, runs the text-extraction and
    chunking stage, then dispatches embedding batches to the embedding
    SQS queue.

    Each embedding batch message has the form:
        {"document_id": "<uuid>", "chunk_ids": ["<uuid>", ...]}

    The number of chunk IDs per message is controlled by the
    EMBEDDING_BATCH_SIZE environment variable (default 10).
    """

    def __init__(self):
        self._sqs = None

    def _get_sqs_client(self):
        if self._sqs is None:
            self._sqs = boto3.client(
                "sqs",
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
        return self._sqs

    def handle(self, message: dict) -> None:
        body = json.loads(message["Body"])

        try:
            document_key = body["detail"]["object"]["key"]
        except KeyError as e:
            raise DocumentProcessingError(
                f"Malformed message, missing field: {e}"
            ) from e

        logger.info("Received message for document=%s", document_key)
        self._chunk_and_dispatch(document_key)

    def _chunk_and_dispatch(self, document_key: str) -> None:
        try:
            document = Document.objects.get(s3_key=document_key)
        except Document.DoesNotExist:
            raise DocumentProcessingError(
                f"Document with key {document_key} not found in database"
            )

        batch_size = int(os.environ.get("EMBEDDING_BATCH_SIZE", "10"))
        processor = DocumentChunkProcessor(
            document=document,
            chunk_batch_size=batch_size,
        )

        try:
            batches = processor.process()
        except DocumentProcessingError:
            logger.error("Chunking failed for document=%s", document_key)
            raise

        if not batches:
            logger.info(
                "Document %s produced no chunks, nothing to dispatch",
                document.id,
            )
            return

        embedding_queue_url = os.environ["EMBEDDING_SQS_QUEUE_URL"]
        sqs = self._get_sqs_client()

        for chunk_ids in batches:
            sqs.send_message(
                QueueUrl=embedding_queue_url,
                MessageBody=json.dumps(
                    {
                        "document_id": str(document.id),
                        "chunk_ids": chunk_ids,
                    }
                ),
            )

        logger.info(
            "Dispatched %d embedding batch(es) for document %s",
            len(batches),
            document.id,
        )

    def on_success(self, message: dict) -> None:
        logger.info("Chunking message processed successfully")

    def on_error(self, message: dict, exception: Exception) -> None:
        logger.error(
            "Chunking failed for message=%s",
            message.get("MessageId", "unknown"),
            exc_info=exception,
        )

    def cleanup(self) -> None:
        pass
