import json
import logging
import os
import boto3

from workers.handler import Handler
from document.models import Document
from document_page.services.document_page_processor import (
    DocumentPageProcessor,
)

logger = logging.getLogger(__name__)


class DocumentPageSlicingHandler(Handler):
    """
    Handler for processing SQS messages related to slicing documents into pages.
    Expects messages to contain the S3 key of the document to process.
    Workflow:
    1. Retrieve the document from the database using the S3 key.
    2. Process the document into pages.
    3. Persist the pages and update the document status.
    Error Handling:
    - If the document is not found, log an error and skip processing.
    - If any step of the processing fails, log the error and update the
    document status to FAILED.
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
            raise ValueError(f"Malformed message, missing field: {e}") from e

        logger.info("Received message for document=%s", document_key)
        self._chunk_and_dispatch(document_key)

    def _chunk_and_dispatch(self, document_key: str) -> None:
        try:
            document = Document.objects.get(s3_key=document_key)
        except Document.DoesNotExist:
            raise ValueError(
                f"Document with key {document_key} not found in database"
            )

        processor = DocumentPageProcessor(document=document)

        pages = processor.process()

        if not pages:
            logger.info(
                "Document %s produced no pages, nothing to dispatch",
                document.id,
            )
            return

    def on_success(self, message: dict) -> None:
        logger.info("page message processed successfully")

    def on_error(self, message: dict, exception: Exception) -> None:
        logger.error(
            "Page processing failed for message=%s",
            message.get("MessageId", "unknown"),
            exc_info=exception,
        )

    def cleanup(self) -> None:
        pass
