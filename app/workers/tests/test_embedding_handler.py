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


def _make_chunk_data(chunk_index=0, content="text"):
    return {
        "content": content,
        "chunk_index": chunk_index,
        "section_type": "Legal",
        "section_title": content,
        "context_prefix": f"[Legal] {content}",
        "bounding_polygons": [{"page_number": 1, "points": [[0, 0], [1, 1]]}],
    }


def _make_embedding_body(document_id="doc-uuid", chunks=None) -> dict:
    return {
        "document_id": document_id,
        "chunks": chunks or [_make_chunk_data()],
    }


class TestEmbeddingHandlerHandle(SimpleTestCase):
    def setUp(self):
        self.handler = EmbeddingHandler()
        self.handler.service = MagicMock()

    def test_handle_calls_process_batch_with_correct_args(self):
        chunks = [_make_chunk_data(0, "first"), _make_chunk_data(1, "second")]
        message = _make_sqs_message(_make_embedding_body("doc-1", chunks))

        self.handler.handle(message)

        self.handler.service.process_batch.assert_called_once_with(
            "doc-1", chunks
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
        message = _make_sqs_message({"chunks": [_make_chunk_data()]})

        self.handler.handle(message)

        self.handler.service.process_batch.assert_not_called()

    def test_handle_skips_processing_when_chunks_missing(self):
        message = _make_sqs_message({"document_id": "doc-1"})

        self.handler.handle(message)

        self.handler.service.process_batch.assert_not_called()

    def test_handle_skips_processing_when_chunks_empty(self):
        message = _make_sqs_message({"document_id": "doc-1", "chunks": []})

        self.handler.handle(message)

        self.handler.service.process_batch.assert_not_called()

    def test_handle_skips_processing_when_chunks_not_a_list(self):
        message = _make_sqs_message(
            {"document_id": "doc-1", "chunks": "not-a-list"}
        )

        self.handler.handle(message)

        self.handler.service.process_batch.assert_not_called()

    def test_handle_does_not_raise_when_process_batch_raises(self):
        self.handler.service.process_batch.side_effect = RuntimeError("down")
        message = _make_sqs_message(_make_embedding_body())

        self.handler.handle(message)  # should not raise


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
