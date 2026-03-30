import json
import types
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from document_chunk.services.embeddings_processor import (
    BatchEmbeddingResult,
    EmbeddingsProcessor,
    TitanEmbeddingAdapter,
)
from document_chunk.services.exceptions.embedding_exceptions import (
    EmbeddingServiceError,
    EmbeddingThrottledError,
    EmbeddingValidationError,
)


def _client_error(code, http_status=400):
    return ClientError(
        {
            "Error": {"Code": code, "Message": "msg"},
            "ResponseMetadata": {"HTTPStatusCode": http_status},
        },
        "InvokeModel",
    )


class TestTitanEmbeddingAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = TitanEmbeddingAdapter()

    def test_build_requests_yields_correct_payloads(self):
        result = list(self.adapter.build_requests(["hello", "world"]))
        self.assertEqual(
            result, [{"inputText": "hello"}, {"inputText": "world"}]
        )

    def test_build_requests_is_a_lazy_generator(self):
        result = self.adapter.build_requests(["text"])
        self.assertIsInstance(result, types.GeneratorType)

    def test_parse_response_returns_embedding_vector(self):
        body = json.dumps({"embedding": [0.1, 0.2, 0.3]}).encode()
        self.assertEqual(self.adapter.parse_response(body), [0.1, 0.2, 0.3])

    def test_parse_response_raises_on_missing_embedding_key(self):
        body = json.dumps({"inputTextTokenCount": 5}).encode()
        with self.assertRaises(EmbeddingValidationError):
            self.adapter.parse_response(body)

    def test_parse_response_raises_on_empty_embedding_list(self):
        body = json.dumps({"embedding": []}).encode()
        with self.assertRaises(EmbeddingValidationError):
            self.adapter.parse_response(body)


class TestBatchEmbeddingResult(unittest.TestCase):
    def test_success_count_counts_non_none_embeddings(self):
        result = BatchEmbeddingResult(
            embeddings=[[0.1], None, [0.3]], errors={}
        )
        self.assertEqual(result.success_count, 2)

    def test_failed_indices_returns_error_keys(self):
        result = BatchEmbeddingResult(
            embeddings=[None, [0.2]], errors={0: RuntimeError("fail")}
        )
        self.assertEqual(result.failed_indices, [0])

    def test_has_errors_returns_true_when_errors_present(self):
        result = BatchEmbeddingResult(
            embeddings=[None], errors={0: Exception()}
        )
        self.assertTrue(result.has_errors())

    def test_has_errors_returns_false_when_no_errors(self):
        result = BatchEmbeddingResult(embeddings=[[0.1]], errors={})
        self.assertFalse(result.has_errors())

    def test_raise_on_errors_raises_runtime_error_with_first_failure(self):
        result = BatchEmbeddingResult(
            embeddings=[None], errors={0: ValueError("cause")}
        )
        with self.assertRaises(RuntimeError):
            result.raise_on_errors()

    def test_raise_on_errors_does_not_raise_when_no_errors(self):
        result = BatchEmbeddingResult(embeddings=[[0.1]], errors={})
        result.raise_on_errors()  # must not raise


class TestEmbeddingsProcessor(unittest.TestCase):
    def setUp(self):
        with patch("boto3.client") as mock_boto:
            self.processor = EmbeddingsProcessor(
                max_retries=2, initial_backoff=0.0
            )
            self.mock_client = mock_boto.return_value

    def _mock_invoke(self, body_bytes):
        mock_body = MagicMock()
        mock_body.read.return_value = body_bytes
        self.mock_client.invoke_model.return_value = {"body": mock_body}

    # --- get_embedding ---

    def test_get_embedding_returns_first_vector(self):
        self._mock_invoke(json.dumps({"embedding": [0.1, 0.2]}).encode())
        result = self.processor.get_embedding("hello world")
        self.assertEqual(result, [0.1, 0.2])

    def test_get_embedding_raises_on_bedrock_error(self):
        # _invoke_with_retry raises EmbeddingThrottledError after retries;
        # embed_batch catches it and records it as an error in the result;
        # get_embedding then calls raise_on_errors() which raises RuntimeError.
        self.mock_client.invoke_model.side_effect = _client_error(
            "ThrottlingException", 429
        )
        with patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                self.processor.get_embedding("hello")

    # --- embed_batch ---

    def test_embed_batch_returns_embeddings_for_all_inputs(self):
        self._mock_invoke(json.dumps({"embedding": [0.5, 0.6]}).encode())
        result = self.processor.embed_batch(["text1", "text2"])
        self.assertEqual(result.success_count, 2)
        self.assertFalse(result.has_errors())

    def test_embed_batch_empty_input_returns_empty_result(self):
        result = self.processor.embed_batch([])
        self.assertEqual(result.success_count, 0)
        self.assertFalse(result.has_errors())

    def test_embed_batch_accumulates_throttle_count_across_futures(self):
        body = json.dumps({"embedding": [0.1]}).encode()
        with patch.object(
            self.processor, "_invoke_with_retry", return_value=(body, 3)
        ):
            result = self.processor.embed_batch(["text"])
        self.assertEqual(result.throttle_count, 3)

    def test_embed_batch_records_error_per_failed_future(self):
        self.mock_client.invoke_model.side_effect = _client_error(
            "ThrottlingException", 429
        )
        with patch("time.sleep"):
            result = self.processor.embed_batch(["text"])
        self.assertTrue(result.has_errors())
        self.assertIsNone(result.embeddings[0])

    # --- _invoke_with_retry ---

    def test_invoke_with_retry_returns_body_and_zero_throttles_on_success(
        self,
    ):
        self._mock_invoke(b"raw_response")
        body, throttle_count = self.processor._invoke_with_retry(
            {"inputText": "hi"}
        )
        self.assertEqual(body, b"raw_response")
        self.assertEqual(throttle_count, 0)

    def test_invoke_with_retry_sends_correct_payload_to_bedrock(self):
        self._mock_invoke(b"response")
        self.processor._invoke_with_retry({"inputText": "hello"})
        call_kwargs = self.mock_client.invoke_model.call_args[1]
        self.assertEqual(call_kwargs["modelId"], self.processor.model_id)
        self.assertIn('"inputText": "hello"', call_kwargs["body"])

    def test_invoke_with_retry_retries_on_throttling_and_succeeds(self):
        mock_body = MagicMock()
        mock_body.read.return_value = b"ok"
        self.mock_client.invoke_model.side_effect = [
            _client_error("ThrottlingException", 429),
            {"body": mock_body},
        ]
        with patch("time.sleep"):
            body, throttle_count = self.processor._invoke_with_retry(
                {"inputText": "t"}
            )
        self.assertEqual(body, b"ok")
        self.assertEqual(throttle_count, 1)

    def test_invoke_with_retry_raises_throttled_after_all_retries_exhausted(
        self,
    ):
        self.mock_client.invoke_model.side_effect = _client_error(
            "ThrottlingException", 429
        )
        with patch("time.sleep"):
            with self.assertRaises(EmbeddingThrottledError):
                self.processor._invoke_with_retry({"inputText": "t"})

    def test_invoke_with_retry_raises_immediately_on_non_retryable_error(self):
        self.mock_client.invoke_model.side_effect = _client_error(
            "ValidationException", 400
        )
        with self.assertRaises(EmbeddingServiceError):
            self.processor._invoke_with_retry({"inputText": "t"})
        self.mock_client.invoke_model.assert_called_once()

    def test_invoke_with_retry_raises_service_error_after_service_unavailable_retries(
        self,
    ):
        self.mock_client.invoke_model.side_effect = _client_error(
            "ServiceUnavailableException", 503
        )
        with patch("time.sleep"):
            with self.assertRaises(EmbeddingServiceError):
                self.processor._invoke_with_retry({"inputText": "t"})
