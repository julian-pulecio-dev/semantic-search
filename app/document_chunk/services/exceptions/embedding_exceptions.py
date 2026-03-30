from botocore.exceptions import BotoCoreError, ClientError

from core.exceptions.base_exception_handler import BaseErrorHandler


class EmbeddingError(Exception):
    """Base domain exception for embedding errors."""

    pass


class EmbeddingThrottledError(EmbeddingError):
    """Raised when Bedrock throttles the request."""

    pass


class EmbeddingModelError(EmbeddingError):
    """Raised when the model itself fails or is unavailable."""

    pass


class EmbeddingServiceError(EmbeddingError):
    """Raised for unclassified or infrastructure-level Bedrock errors."""

    pass


class EmbeddingValidationError(EmbeddingError):
    """Raised when the model response is malformed or missing the embedding."""

    pass


EMBEDDING_ERROR_MAP: dict[str, type[EmbeddingError]] = {
    "ThrottlingException": EmbeddingThrottledError,
    "RequestLimitExceeded": EmbeddingThrottledError,
    "ModelTimeoutException": EmbeddingModelError,
    "ModelNotReadyException": EmbeddingModelError,
    "ModelErrorException": EmbeddingModelError,
    "ServiceUnavailableException": EmbeddingServiceError,
}


def map_bedrock_exception(e: ClientError) -> EmbeddingError:
    """
    Maps a boto3 ClientError to a domain EmbeddingError based on the
    error code and HTTP status. Falls back to EmbeddingServiceError
    for unrecognised errors.

    Args:
        e: The original ClientError raised by boto3.
    Returns:
        An EmbeddingError subclass instance with context about the failure.
    """
    error = e.response.get("Error", {})
    error_code = error.get("Code")
    http_status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

    if error_code in EMBEDDING_ERROR_MAP:
        return EMBEDDING_ERROR_MAP[error_code](f"Bedrock error: {error_code}")

    if http_status == 429:
        return EmbeddingThrottledError("Bedrock rate limit exceeded")

    if http_status in (500, 502, 503, 504):
        return EmbeddingServiceError("Bedrock internal service error")

    return EmbeddingServiceError(
        f"Unhandled Bedrock error: {error_code or http_status}"
    )


class EmbeddingErrorHandler(BaseErrorHandler):
    catches = (ClientError, BotoCoreError)

    def handle(self, exc: Exception) -> EmbeddingError:
        if isinstance(exc, ClientError):
            return map_bedrock_exception(exc)
        return EmbeddingServiceError(f"Low-level boto3 error: {exc}")


handle_embedding_errors = EmbeddingErrorHandler()
