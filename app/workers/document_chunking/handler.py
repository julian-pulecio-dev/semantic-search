import json
import logging
from workers.handler import Handler
from document_chunk.models import Document
from document_chunk.services.document_chunk_processor import (
    DocumentChunkProcessor,
    DocumentProcessingError,
)


class DocumentChunkingHandler(Handler):
    """
    Business logic handler responsible for document chunking.

    This class contains ONLY domain logic.
    No SQS, threading or infrastructure concerns.
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def handle(self, message: dict) -> None:
        """
        Process one SQS message.
        Args:
            message: The SQS message dict.
        Raises:
            DocumentProcessingError: If processing fails at any step.
        """

        body = json.loads(message["Body"])

        self.logger.info(f"Received message for {body}")

        document_key = body["detail"]["object"]["key"]

        self.logger.info(f"Starting chunking for document={document_key}")

        self.chunk_document(document_key)

    def chunk_document(self, document_key: str) -> None:
        """
        Core domain logic for fetching, parsing, chunking and embedding a document.
        Args:
            document_key: The key of the Document to process.
        Raises:
            DocumentProcessingError: If any step of the processing fails.
        """
        try:
            document = Document.objects.get(s3_key=document_key)
            processor = DocumentChunkProcessor(document)
            processor.process()
        except DocumentProcessingError as e:
            self.logger.error(f"Error processing document {document_key}: {e}")
            raise

        self.logger.info(f"Chunking completed for document={document_key}")

    def on_success(self, message: dict) -> None:
        """
        Optional hook for successful message processing.
        Args:
            message: The SQS message dict.
        """
        self.logger.info("Message processed successfully")

    def on_error(self, message: dict, exception: Exception) -> None:
        """
        Optional hook for handling exceptions during message processing.
        Args:
            message: The SQS message dict.
            exception: The exception that was raised.
        """
        self.logger.error(
            "Document processing failed",
            exc_info=exception,
        )

    def cleanup(self) -> None:
        """
        Optional per-message cleanup.
        """
        pass
