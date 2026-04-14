import json
import logging
import os
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

    def test_handle_calls_chunk_and_dispatch_with_correct_key(self):
        message = _make_sqs_message(_make_s3_event_body("docs/my-file.pdf"))
        self.handler._chunk_and_dispatch = MagicMock()

        self.handler.handle(message)

        self.handler._chunk_and_dispatch.assert_called_once_with(
            "docs/my-file.pdf"
        )

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

        with self.assertRaises(DocumentProcessingError):
            self.handler.handle(message)

    def test_handle_propagates_document_processing_error(self):
        message = _make_sqs_message(_make_s3_event_body("docs/bad.pdf"))
        self.handler._chunk_and_dispatch = MagicMock(
            side_effect=DocumentProcessingError("cannot fetch")
        )

        with self.assertRaises(DocumentProcessingError):
            self.handler.handle(message)


class TestDocumentChunkingHandlerChunkAndDispatch(SimpleTestCase):
    def setUp(self):
        self.handler = DocumentChunkingHandler()

    @patch("workers.document_chunking.handler.boto3.client")
    @patch("workers.document_chunking.handler.DocumentChunkProcessor")
    @patch("workers.document_chunking.handler.Document")
    def test_fetches_document_and_calls_process(
        self, mock_document_cls, mock_processor_cls, mock_boto3
    ):
        mock_document = MagicMock()
        mock_document_cls.objects.get.return_value = mock_document
        mock_processor = MagicMock()
        mock_processor.process.return_value = []
        mock_processor_cls.return_value = mock_processor

        with patch.dict(
            os.environ, {"EMBEDDING_SQS_QUEUE_URL": "http://sqs/embed"}
        ):
            self.handler._chunk_and_dispatch("docs/test.pdf")

        mock_document_cls.objects.get.assert_called_once_with(
            s3_key="docs/test.pdf"
        )
        mock_processor.process.assert_called_once()

    @patch("workers.document_chunking.handler.boto3.client")
    @patch("workers.document_chunking.handler.DocumentChunkProcessor")
    @patch("workers.document_chunking.handler.Document")
    def test_sends_one_sqs_message_per_batch(
        self, mock_document_cls, mock_processor_cls, mock_boto3
    ):
        mock_document = MagicMock()
        mock_document.id = "doc-uuid"
        mock_document_cls.objects.get.return_value = mock_document

        batch1 = ["id1", "id2"]
        batch2 = ["id3"]
        mock_processor_cls.return_value.process.return_value = [batch1, batch2]

        mock_sqs = MagicMock()
        mock_boto3.return_value = mock_sqs

        with patch.dict(
            os.environ, {"EMBEDDING_SQS_QUEUE_URL": "http://sqs/embed"}
        ):
            self.handler._chunk_and_dispatch("docs/test.pdf")

        self.assertEqual(mock_sqs.send_message.call_count, 2)

        first_call_body = json.loads(
            mock_sqs.send_message.call_args_list[0][1]["MessageBody"]
        )
        self.assertEqual(first_call_body["document_id"], "doc-uuid")
        self.assertEqual(first_call_body["chunk_ids"], batch1)

        second_call_body = json.loads(
            mock_sqs.send_message.call_args_list[1][1]["MessageBody"]
        )
        self.assertEqual(second_call_body["chunk_ids"], batch2)

    @patch("workers.document_chunking.handler.boto3.client")
    @patch("workers.document_chunking.handler.DocumentChunkProcessor")
    @patch("workers.document_chunking.handler.Document")
    def test_does_not_send_sqs_when_no_batches(
        self, mock_document_cls, mock_processor_cls, mock_boto3
    ):
        mock_document_cls.objects.get.return_value = MagicMock()
        mock_processor_cls.return_value.process.return_value = []
        mock_sqs = MagicMock()
        mock_boto3.return_value = mock_sqs

        with patch.dict(
            os.environ, {"EMBEDDING_SQS_QUEUE_URL": "http://sqs/embed"}
        ):
            self.handler._chunk_and_dispatch("docs/empty.pdf")

        mock_sqs.send_message.assert_not_called()

    @patch("workers.document_chunking.handler.DocumentChunkProcessor")
    @patch("workers.document_chunking.handler.Document")
    def test_raises_when_document_not_found(
        self, mock_document_cls, mock_processor_cls
    ):
        mock_document_cls.objects.get.side_effect = Exception("DoesNotExist")

        with self.assertRaises(Exception):
            self.handler._chunk_and_dispatch("docs/missing.pdf")

    @patch("workers.document_chunking.handler.DocumentChunkProcessor")
    @patch("workers.document_chunking.handler.Document")
    def test_reraises_document_processing_error_from_process(
        self, mock_document_cls, mock_processor_cls
    ):
        mock_document_cls.objects.get.return_value = MagicMock()
        mock_processor_cls.return_value.process.side_effect = (
            DocumentProcessingError("failed")
        )

        with self.assertRaises(DocumentProcessingError):
            self.handler._chunk_and_dispatch("docs/bad.pdf")

    @patch("workers.document_chunking.handler.DocumentChunkProcessor")
    @patch("workers.document_chunking.handler.Document")
    def test_uses_embedding_batch_size_from_env(
        self, mock_document_cls, mock_processor_cls
    ):
        mock_document = MagicMock()
        mock_document_cls.objects.get.return_value = mock_document
        mock_processor_cls.return_value.process.return_value = []

        with patch.dict(
            os.environ,
            {
                "EMBEDDING_BATCH_SIZE": "5",
                "EMBEDDING_SQS_QUEUE_URL": "http://sqs/embed",
            },
        ):
            self.handler._chunk_and_dispatch("docs/test.pdf")

        _, kwargs = mock_processor_cls.call_args
        self.assertEqual(kwargs["chunk_batch_size"], 5)


class TestDocumentChunkingHandlerHooks(SimpleTestCase):
    def setUp(self):
        self.handler = DocumentChunkingHandler()

    def test_on_success_does_not_raise(self):
        self.handler.on_success(_make_sqs_message(_make_s3_event_body()))

    def test_on_error_does_not_raise(self):
        self.handler.on_error(
            _make_sqs_message(_make_s3_event_body()), ValueError("something")
        )

    def test_cleanup_does_not_raise(self):
        self.handler.cleanup()
