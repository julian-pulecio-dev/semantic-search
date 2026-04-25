import json
import logging
import os
import boto3

from workers.handler import Handler
from document_page.models import DocumentPage
from document_chunk.services.page_chunk_processor import (
    PageChunkProcessor,
)
from document.services.exceptions.document_exceptions import (
    DocumentProcessingError,
)

logger = logging.getLogger(__name__)


class DocumentChunkingHandler(Handler):
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
            page_key = body["detail"]["object"]["key"]
        except KeyError as e:
            raise ValueError(
                f"Malformed message, missing field: {e}"
            ) from e

        logger.info("Received message for page=%s", page_key)
        self._chunk_and_dispatch(page_key)

    def _chunk_and_dispatch(self, page_key: str) -> None:
        try:
            page = DocumentPage.objects.get(s3_key=page_key)
        except DocumentPage.DoesNotExist:
            raise ValueError(
                f"Page with key {page_key} not found in database"
            )

        processor = PageChunkProcessor(page=page, document=page.document)

        chunks = processor.process()

        if not chunks:
            logger.info(
                "Page %s produced no chunks, nothing to dispatch",
                page.id,
            )
            return

    def on_success(self, message: dict) -> None:
        logger.info("chunk message processed successfully")

    def on_error(self, message: dict, exception: Exception) -> None:
        logger.error(
            "Page processing failed for message=%s",
            message.get("MessageId", "unknown"),
            exc_info=exception,
        )

    def cleanup(self) -> None:
        pass
