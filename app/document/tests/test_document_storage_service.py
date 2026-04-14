import unittest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError, BotoCoreError
from document.services.exceptions.storage_exceptions import (
    S3FileNotFoundError,
    S3ServiceError,
)

from document.services.storage import S3FileLoaderService


class TestS3FileLoaderService(unittest.TestCase):

    def setUp(self):
        self.bucket_name = "test-bucket"
        self.patcher = patch("document.services.storage.boto3.client")
        self.mock_boto_client = self.patcher.start()
        self.mock_s3 = self.mock_boto_client.return_value
        self.service = S3FileLoaderService(self.bucket_name)

    def tearDown(self):
        self.patcher.stop()

    def test_build_document_key(self):
        """Verify that the document key is built correctly based on user ID and
        document ID."""

        result = self.service.build_document_key(1, 100)
        self.assertEqual(result, "documents/1/100")

    def test_file_exists_success(self):
        """Verify that file_exists returns True when the file is found in
        S3."""

        self.mock_s3.head_object.return_value = {}
        exists = self.service.file_exists("test-key")
        self.assertTrue(exists)
        self.mock_s3.head_object.assert_called_with(
            Bucket=self.bucket_name, Key="test-key"
        )

    @patch("document.services.storage.map_s3_exception")
    def test_file_exists_not_found(self, mock_map):
        """Verify that file_exists returns False when the file is not found in
        S3."""

        error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
        self.mock_s3.head_object.side_effect = ClientError(
            error_response, "HeadObject"
        )
        mock_map.return_value = S3FileNotFoundError("Not found")

        exists = self.service.file_exists("missing-key")
        self.assertFalse(exists)

    def test_file_exists_botocore_error(self):
        """Verify that file_exists raises S3ServiceError when a BotoCoreError
        occurs."""

        self.mock_s3.head_object.side_effect = BotoCoreError()
        with self.assertRaises(S3ServiceError):
            self.service.file_exists("test-key")

    def test_get_file_success(self):
        """Verify that get_file retrieves file content successfully."""

        mock_body = MagicMock()
        mock_body.read.return_value = b"file content"
        self.mock_s3.get_object.return_value = {"Body": mock_body}

        result = self.service.get_file("test-key")
        self.assertEqual(result, b"file content")
        self.mock_s3.get_object.assert_called_once_with(
            Bucket=self.bucket_name, Key="test-key"
        )

    def test_delete_file_success(self):
        """Verify that delete_file deletes the file successfully."""

        self.mock_s3.delete_object.return_value = {}
        result = self.service.delete_file("test-key")
        self.assertTrue(result)
        self.mock_s3.delete_object.assert_called_once_with(
            Bucket=self.bucket_name, Key="test-key"
        )

    def test_generate_presigned_url_success(self):
        """Verify that generate_presigned_url_for_upload returns the expected
        presigned URL and fields."""

        s3_response = {"url": "https://s3.url", "fields": {}}
        self.mock_s3.generate_presigned_post.return_value = s3_response

        user_id = "test-user-id"
        upload_session_id = "test-upload-session-id"
        document_id = "test-document-id"
        key = "test-key"

        result = self.service.generate_presigned_url_for_upload(
            upload_session_id=upload_session_id,
            document_id=document_id,
            key=key,
            user_id=user_id,
        )

        expected_response = {
            **s3_response,
            "upload_session_id": upload_session_id,
            "document_id": document_id,
        }
        self.assertEqual(result, expected_response)

        self.mock_s3.generate_presigned_post.assert_called_once()
        args, kwargs = self.mock_s3.generate_presigned_post.call_args
        self.assertEqual(kwargs["Bucket"], self.bucket_name)
        self.assertEqual(kwargs["Fields"]["x-amz-meta-user-id"], user_id)
