from functools import wraps
from botocore.exceptions import ClientError, BotoCoreError


class DocumentStorageError(Exception):
    """Base domain exception for storage errors."""

    pass


class S3FileNotFoundError(DocumentStorageError):
    pass


class S3AccessDeniedError(DocumentStorageError):
    pass


class S3BucketError(DocumentStorageError):
    pass


class S3UploadError(DocumentStorageError):
    pass


class S3RateLimitError(DocumentStorageError):
    pass


class S3ServiceError(DocumentStorageError):
    pass


NOT_FOUND_ERRORS = {
    "NoSuchKey",
    "NoSuchBucket",
    "NotFound",
}

ACCESS_ERRORS = {
    "AccessDenied",
    "SignatureDoesNotMatch",
    "InvalidAccessKeyId",
    "InvalidToken",
}

BUCKET_ERRORS = {
    "BucketAlreadyExists",
    "InvalidBucketName",
}

UPLOAD_ERRORS = {
    "EntityTooLarge",
    "InvalidObjectState",
}

RATE_LIMIT_ERRORS = {
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "RequestLimitExceeded",
}

ERROR_GROUPS = {
    S3FileNotFoundError: NOT_FOUND_ERRORS,
    S3AccessDeniedError: ACCESS_ERRORS,
    S3BucketError: BUCKET_ERRORS,
    S3UploadError: UPLOAD_ERRORS,
    S3RateLimitError: RATE_LIMIT_ERRORS,
}

ERROR_CODE_MAP = {
    code: exc for exc, codes in ERROR_GROUPS.items() for code in codes
}


def map_s3_exception(e: ClientError):
    """Map a boto3 ClientError to a custom domain exception based on error code
    and HTTP status.

    Arguments:
        e (ClientError): The original exception raised by boto3.
    Returns:
        DocumentStorageError: A mapped custom exception that provides
                              more context about the S3 error.
    """

    error = e.response.get("Error", {})
    error_code = error.get("Code")
    http_status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

    if error_code in ERROR_CODE_MAP:
        return ERROR_CODE_MAP[error_code](f"S3 Error: {error_code}")

    if http_status == 404:
        return S3FileNotFoundError("S3 resource not found")

    if http_status == 403:
        return S3AccessDeniedError("Access denied to S3 resource")

    if http_status == 429:
        return S3RateLimitError("S3 rate limit exceeded")

    if http_status in (500, 502, 503, 504):
        return S3ServiceError("S3 internal service error")

    return S3ServiceError(f"Unhandled S3 error: {error_code or http_status}")


def handle_storage_errors(func):
    """Decorator to wrap storage operations and handle S3 exceptions
    gracefully."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)

        except ClientError as e:
            raise map_s3_exception(e) from e

        except BotoCoreError as e:
            raise S3ServiceError("Low-level boto3 error") from e

    return wrapper
