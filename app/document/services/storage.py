import boto3
from document.exceptions.storage_exceptions import (
    S3FileNotFoundError,
    map_s3_exception,
    S3ServiceError,
    handle_storage_errors,
)
from botocore.exceptions import ClientError
from botocore.exceptions import BotoCoreError


class S3FileLoader:
    """Service class for handling S3 file operations with robust error handling."""

    def __init__(self, bucket_name):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3")

    def file_exists(self, key: str) -> bool:
        """
        Check if a file exists in S3 by attempting to retrieve its metadata.
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
        """
        Retrieve a file from S3 and return its content as bytes.
        Arguments:
            key (str): The S3 key of the file to retrieve.
        Returns:
            bytes: The content of the file.
        """

        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()

    @handle_storage_errors
    def delete_file(self, key: str):
        """
        Delete a file from S3.
        Arguments:
            key (str): The S3 key of the file to delete.
        Returns:
            bool: True if the file was deleted successfully.
        """

        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
        return True

    @handle_storage_errors
    def generate_presigned_url_for_upload(
        self, key: str, expiration: int = 3600, user_email: str = None
    ) -> str:
        """
        Generate a presigned URL for uploading a file to S3.
        Arguments:
            key (str): The S3 key of the file for which to generate the URL.
            expiration (int): Time in seconds for the presigned URL to remain valid.
            user_email (str): The email of the user uploading the file.
        Returns:
            str: The generated presigned URL.
        """

        max_size = 20 * 1024 * 1024  # 20 MB
        key = str(key)

        response = self.s3_client.generate_presigned_post(
            Bucket=self.bucket_name,
            Key=key,
            Fields={
                "key": key,
                "Content-Type": "application/pdf",
                "acl": "private",
                "x-amz-meta-document-id": str(key),
                "x-amz-meta-user-email": str(user_email),
                "x-amz-server-side-encryption": "AES256",
            },
            Conditions=[
                {"Content-Type": "application/pdf"},
                {"acl": "private"},
                {"x-amz-meta-document-id": str(key)},
                {"x-amz-meta-user-email": str(user_email)},
                {"x-amz-server-side-encryption": "AES256"},
                ["starts-with", "$key", f"{user_email}/"],
                ["content-length-range", 1, max_size],
            ],
            ExpiresIn=expiration,
        )

        return response
