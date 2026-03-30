import unittest

from botocore.exceptions import BotoCoreError, ClientError
from django.db import DatabaseError
from django.test import TestCase

from document_chunk.services.exceptions.embedding_exceptions import (
    EmbeddingError,
    EmbeddingModelError,
    EmbeddingServiceError,
    EmbeddingThrottledError,
    handle_embedding_errors,
    map_bedrock_exception,
)
from document_chunk.services.exceptions.document_chunk_exceptions import (
    DocumentPersistenceError,
    handle_persistence_errors,
)


def _client_error(code, http_status=400):
    return ClientError(
        {
            "Error": {"Code": code, "Message": "Test error"},
            "ResponseMetadata": {"HTTPStatusCode": http_status},
        },
        "InvokeModel",
    )


class TestMapBedrockException(unittest.TestCase):
    def test_throttling_exception_maps_to_throttled_error(self):
        result = map_bedrock_exception(_client_error("ThrottlingException"))
        self.assertIsInstance(result, EmbeddingThrottledError)

    def test_request_limit_exceeded_maps_to_throttled_error(self):
        result = map_bedrock_exception(_client_error("RequestLimitExceeded"))
        self.assertIsInstance(result, EmbeddingThrottledError)

    def test_model_timeout_maps_to_model_error(self):
        result = map_bedrock_exception(_client_error("ModelTimeoutException"))
        self.assertIsInstance(result, EmbeddingModelError)

    def test_model_not_ready_maps_to_model_error(self):
        result = map_bedrock_exception(_client_error("ModelNotReadyException"))
        self.assertIsInstance(result, EmbeddingModelError)

    def test_service_unavailable_maps_to_service_error(self):
        result = map_bedrock_exception(
            _client_error("ServiceUnavailableException")
        )
        self.assertIsInstance(result, EmbeddingServiceError)

    def test_http_429_maps_to_throttled_error_for_unknown_code(self):
        result = map_bedrock_exception(
            _client_error("UnknownCode", http_status=429)
        )
        self.assertIsInstance(result, EmbeddingThrottledError)

    def test_http_500_maps_to_service_error(self):
        result = map_bedrock_exception(
            _client_error("UnknownCode", http_status=500)
        )
        self.assertIsInstance(result, EmbeddingServiceError)

    def test_http_503_maps_to_service_error(self):
        result = map_bedrock_exception(
            _client_error("UnknownCode", http_status=503)
        )
        self.assertIsInstance(result, EmbeddingServiceError)

    def test_unrecognised_code_and_status_maps_to_service_error(self):
        result = map_bedrock_exception(
            _client_error("SomeRandomError", http_status=400)
        )
        self.assertIsInstance(result, EmbeddingServiceError)

    def test_all_results_are_subclasses_of_embedding_error(self):
        for code in (
            "ThrottlingException",
            "ModelTimeoutException",
            "ServiceUnavailableException",
        ):
            with self.subTest(code=code):
                result = map_bedrock_exception(_client_error(code))
                self.assertIsInstance(result, EmbeddingError)


class TestHandleEmbeddingErrors(unittest.TestCase):
    def test_translates_client_error_to_embedding_error(self):
        @handle_embedding_errors
        def failing():
            raise _client_error("ThrottlingException", 429)

        with self.assertRaises(EmbeddingError):
            failing()

    def test_translates_botocore_error_to_service_error(self):
        @handle_embedding_errors
        def failing():
            raise BotoCoreError()

        with self.assertRaises(EmbeddingServiceError):
            failing()

    def test_does_not_swallow_other_exceptions(self):
        @handle_embedding_errors
        def failing():
            raise ValueError("not a boto error")

        with self.assertRaises(ValueError):
            failing()

    def test_passes_through_return_value_on_success(self):
        @handle_embedding_errors
        def successful():
            return [0.1, 0.2]

        self.assertEqual(successful(), [0.1, 0.2])

    def test_preserves_function_name_via_wraps(self):
        @handle_embedding_errors
        def my_func():
            pass

        self.assertEqual(my_func.__name__, "my_func")


class TestHandlePersistenceErrors(TestCase):
    def test_translates_database_error_to_persistence_error(self):
        @handle_persistence_errors
        def failing():
            raise DatabaseError("db error")

        with self.assertRaises(DocumentPersistenceError):
            failing()

    def test_does_not_swallow_other_exceptions(self):
        @handle_persistence_errors
        def failing():
            raise RuntimeError("not a db error")

        with self.assertRaises(RuntimeError):
            failing()

    def test_passes_through_return_value_on_success(self):
        @handle_persistence_errors
        def successful():
            return "ok"

        self.assertEqual(successful(), "ok")

    def test_preserves_function_name_via_wraps(self):
        @handle_persistence_errors
        def my_func():
            pass

        self.assertEqual(my_func.__name__, "my_func")
