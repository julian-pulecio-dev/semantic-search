import json
import logging
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from workers.document_chunking.handler import DocumentChunkingHandler
from document_chunk.services.document_chunk_processor import (
    DocumentProcessingError,
)

logging.disable(logging.CRITICAL)


def _make_sqs_message(body: dict) -> dict:
    return {
        "MessageId": "msg-1",
        "ReceiptHandle": "rh-1",
        "Body": json.dumps(body),
    }


def _make_s3_event_body(key: str = "documents/test.pdf") -> dict:
    return {"detail": {"object": {"key": key}}}


class TestDocumentChunkingHandlerHandle(SimpleTestCase):
    def setUp(self):
        self.handler = DocumentChunkingHandler()

    def test_handle_calls_chunk_document_with_correct_key(self):
        message = _make_sqs_message(_make_s3_event_body("docs/my-file.pdf"))
        self.handler.chunk_document = MagicMock()

        self.handler.handle(message)

        self.handler.chunk_document.assert_called_once_with("docs/my-file.pdf")

    def test_handle_raises_on_invalid_json_body(self):
        message = {
            "MessageId": "msg-1",
            "ReceiptHandle": "rh-1",
            "Body": "not-json",
        }

        with self.assertRaises(json.JSONDecodeError):
            self.handler.handle(message)

    def test_handle_raises_on_missing_detail_key(self):
        message = _make_sqs_message({"unexpected": "shape"})

        with self.assertRaises(KeyError):
            self.handler.handle(message)

    def test_handle_propagates_document_processing_error(self):
        message = _make_sqs_message(_make_s3_event_body("docs/bad.pdf"))
        self.handler.chunk_document = MagicMock(
            side_effect=DocumentProcessingError("cannot fetch")
        )

        with self.assertRaises(DocumentProcessingError):
            self.handler.handle(message)


class TestDocumentChunkingHandlerChunkDocument(SimpleTestCase):
    def setUp(self):
        self.handler = DocumentChunkingHandler()

    @patch("workers.document_chunking.handler.DocumentChunkProcessor")
    @patch("workers.document_chunking.handler.Document")
    def test_chunk_document_fetches_document_and_calls_process(
        self, mock_document_cls, mock_processor_cls
    ):
        mock_document = MagicMock()
        mock_document_cls.objects.get.return_value = mock_document

        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        self.handler.chunk_document("docs/test.pdf")

        mock_document_cls.objects.get.assert_called_once_with(
            s3_key="docs/test.pdf"
        )
        # DocumentChunkProcessor is a dataclass — called with document as the
        # only positional argument; optional fields use their defaults.
        mock_processor_cls.assert_called_once_with(mock_document)
        mock_processor.process.assert_called_once()

    @patch("workers.document_chunking.handler.DocumentChunkProcessor")
    @patch("workers.document_chunking.handler.Document")
    def test_chunk_document_reraises_error_from_process(
        self, mock_document_cls, mock_processor_cls
    ):
        """DocumentProcessingError raised by process() is caught and re-raised."""
        mock_document_cls.objects.get.return_value = MagicMock()
        mock_processor_cls.return_value.process.side_effect = (
            DocumentProcessingError("save failed")
        )

        with self.assertRaises(DocumentProcessingError):
            self.handler.chunk_document("docs/bad.pdf")

    @patch("workers.document_chunking.handler.DocumentChunkProcessor")
    @patch("workers.document_chunking.handler.Document")
    def test_chunk_document_reraises_error_from_processor_init(
        self, mock_document_cls, mock_processor_cls
    ):
        """DocumentProcessingError raised during processor construction
        (e.g. _update_document_status failing in __post_init__) is caught
        and re-raised."""
        mock_document_cls.objects.get.return_value = MagicMock()
        mock_processor_cls.side_effect = DocumentProcessingError(
            "status update failed"
        )

        with self.assertRaises(DocumentProcessingError):
            self.handler.chunk_document("docs/test.pdf")

    @patch("workers.document_chunking.handler.Document")
    def test_chunk_document_raises_when_document_not_found(
        self, mock_document_cls
    ):
        mock_document_cls.objects.get.side_effect = Exception("DoesNotExist")

        with self.assertRaises(Exception):
            self.handler.chunk_document("docs/missing.pdf")


class TestDocumentChunkingHandlerHooks(SimpleTestCase):
    def setUp(self):
        self.handler = DocumentChunkingHandler()

    def test_on_success_does_not_raise(self):
        message = _make_sqs_message(_make_s3_event_body())
        self.handler.on_success(message)

    def test_on_error_does_not_raise(self):
        message = _make_sqs_message(_make_s3_event_body())
        self.handler.on_error(message, ValueError("something"))

    def test_cleanup_does_not_raise(self):
        self.handler.cleanup()
