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
            ],
        }


    Chunks are NOT persisted here. The embedding worker persists each chunk,
    attaches embeddings, and resolves bounding polygons.
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

        processor = DocumentChunkProcessor(document=document)

        batches = processor.process()

        if not batches:
            logger.info(
                "Document %s produced no chunks, nothing to dispatch",
                document.id,
            )
            return

        # Set number_of_pages before dispatching so the embedding worker can
        # finalise document status as soon as the last batch is done.
        document.number_of_pages = len(batches)
        document.save(update_fields=["number_of_pages"])

        embedding_queue_url = os.environ["EMBEDDING_SQS_QUEUE_URL"]
        sqs = self._get_sqs_client()

        for batch in batches:
            sqs.send_message(
                QueueUrl=embedding_queue_url,
                MessageBody=json.dumps(
                    {
                        "document_id": str(document.id),
                        "chunks": [chunk.to_dict() for chunk in batch],
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
