import json
import logging
from workers.handler import Handler


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
        """

        body = json.loads(message["Body"])

        document_id = body["document_id"]

        self.logger.info(f"Starting chunking for document={document_id}")

        self.chunk_document(document_id)

    def chunk_document(self, document_id: str) -> None:
        """
        Actual domain logic.
        Replace with your real implementation.
        """

        self.logger.info(f"Chunking completed for document={document_id}")

    def on_success(self, message: dict) -> None:
        self.logger.info("Message processed successfully")

    def on_error(self, message: dict, exception: Exception) -> None:
        self.logger.error(
            "Document processing failed",
            exc_info=exception,
        )

    def cleanup(self) -> None:
        """
        Optional per-message cleanup.
        """
        pass
