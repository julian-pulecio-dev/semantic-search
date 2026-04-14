import json
import logging
from unittest.mock import MagicMock
from django.test import SimpleTestCase
from workers.embedding.handler import EmbeddingHandler

logging.disable(logging.CRITICAL)


def _make_sqs_message(body: dict) -> dict:
    return {
        "MessageId": "msg-embed-1",
        "ReceiptHandle": "rh-1",
        "Body": json.dumps(body),
    }


def _make_embedding_body(document_id="doc-uuid", chunk_ids=None) -> dict:
    return {
        "document_id": document_id,
        "chunk_ids": chunk_ids or ["chunk-1", "chunk-2"],
    }


class TestEmbeddingHandlerHandle(SimpleTestCase):
    def setUp(self):
        self.handler = EmbeddingHandler()
        self.handler.service = MagicMock()

    def test_handle_calls_process_batch_with_correct_args(self):
        message = _make_sqs_message(
            _make_embedding_body("doc-1", ["c1", "c2", "c3"])
        )

        self.handler.handle(message)

        self.handler.service.process_batch.assert_called_once_with(
            "doc-1", ["c1", "c2", "c3"]
        )

    def test_handle_raises_on_invalid_json_body(self):
        message = {
            "MessageId": "msg-1",
            "ReceiptHandle": "rh-1",
            "Body": "not-json",
        }

        with self.assertRaises(json.JSONDecodeError):
            self.handler.handle(message)

    def test_handle_skips_processing_when_document_id_missing(self):
        message = _make_sqs_message({"chunk_ids": ["c1"]})

        self.handler.handle(message)

        self.handler.service.process_batch.assert_not_called()

    def test_handle_skips_processing_when_chunk_ids_missing(self):
        message = _make_sqs_message({"document_id": "doc-1"})

        self.handler.handle(message)

        self.handler.service.process_batch.assert_not_called()

    def test_handle_skips_processing_when_chunk_ids_empty(self):
        message = _make_sqs_message({"document_id": "doc-1", "chunk_ids": []})

        self.handler.handle(message)

        self.handler.service.process_batch.assert_not_called()

    def test_handle_skips_processing_when_chunk_ids_not_a_list(self):
        message = _make_sqs_message(
            {"document_id": "doc-1", "chunk_ids": "not-a-list"}
        )

        self.handler.handle(message)

        self.handler.service.process_batch.assert_not_called()

    def test_handle_does_not_raise_when_process_batch_raises(self):
        """
        Exceptions from process_batch must not propagate — the message
        should be deleted from SQS after any outcome.
        """
        self.handler.service.process_batch.side_effect = RuntimeError(
            "bedrock down"
        )
        message = _make_sqs_message(_make_embedding_body())

        # Should not raise
        self.handler.handle(message)


class TestEmbeddingHandlerHooks(SimpleTestCase):
    def setUp(self):
        self.handler = EmbeddingHandler()

    def test_on_success_does_not_raise(self):
        self.handler.on_success(_make_sqs_message(_make_embedding_body()))

    def test_on_error_does_not_raise(self):
        self.handler.on_error(
            _make_sqs_message(_make_embedding_body()), RuntimeError("boom")
        )

    def test_cleanup_does_not_raise(self):
        self.handler.cleanup()
