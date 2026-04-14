import boto3
from document.services.exceptions.storage_exceptions import (
    S3FileNotFoundError,
    map_s3_exception,
    S3ServiceError,
    handle_storage_errors,
)
from botocore.exceptions import ClientError
from botocore.exceptions import BotoCoreError


class S3FileLoaderService:
    """Service class for handling S3 file operations with robust error
    handling."""

    def __init__(self, bucket_name):
        self.bucket_name = bucket_name

    @property
    def s3_client(self):
        """Always returns a client with fresh credentials."""
        return boto3.client("s3")

    def build_document_key(self, user_id: int, upload_session_id: int) -> str:
        return f"documents/{user_id}/{upload_session_id}"

    def file_exists(self, key: str) -> bool:
        """Check if a file exists in S3 by attempting to retrieve its metadata.

        Arguments:
            key (str): The S3 key of the file to check.
        Returns:
            bool: True if the file exists, False otherwise.
        """

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            mapped = map_s3_exception(e)
            if isinstance(mapped, S3FileNotFoundError):
                return False
            raise mapped from e
        except BotoCoreError as e:
            raise S3ServiceError("Low-level boto3 error") from e

    @handle_storage_errors
    def get_file(self, key: str) -> bytes:
        """Retrieve a file from S3 and return its content as bytes.

        Arguments:
            key (str): The S3 key of the file to retrieve.
        Returns:
            bytes: The content of the file.
        """

        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()

    @handle_storage_errors
    def delete_file(self, key: str):
        """Delete a file from S3.

        Arguments:
            key (str): The S3 key of the file to delete.
        Returns:
            bool: True if the file was deleted successfully.
        """

        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
        return True

    @handle_storage_errors
    def generate_presigned_url_for_upload(
        self,
        key: str,
        user_id: str,
        upload_session_id: str,
        document_id: str,
        expiration: int = 3600,
    ) -> dict:
        """
        Generate a presigned POST URL for uploading a file to S3
        with enforced metadata for async processing.
        """

        max_size = 20 * 1024 * 1024  # 20 MB
        key = str(key)

        metadata = {
            "x-amz-meta-upload-session-id": str(upload_session_id),
            "x-amz-meta-document-id": str(document_id),
            "x-amz-meta-user-id": str(user_id),
        }

        fields = {
            "key": key,
            "Content-Type": "application/pdf",
            "x-amz-server-side-encryption": "AES256",
            **metadata,
        }

        conditions = [
            {"Content-Type": "application/pdf"},
            {"x-amz-server-side-encryption": "AES256"},
            ["starts-with", "$key", f"documents/{user_id}/"],
            ["content-length-range", 1, max_size],
            *[{k: v} for k, v in metadata.items()],
        ]

        response = self.s3_client.generate_presigned_post(
            Bucket=self.bucket_name,
            Key=key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expiration,
        )

        return {
            **response,
            "upload_session_id": str(upload_session_id),
            "document_id": str(document_id),
        }

    def get_public_url(self, key: str) -> str:
        """Return the public URL for a document stored in S3.

        Arguments:
            key (str): The S3 key of the file.
        Returns:
            str: The public URL of the file.
        """
        region = self.s3_client.meta.region_name
        return f"https://{self.bucket_name}.s3.{region}.amazonaws.com/{key}"
