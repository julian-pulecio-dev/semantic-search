from django.test import TestCase
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from document.services.storage import upload_file_to_s3


class StorageServiceTests(TestCase):

    @patch("document.services.storage.boto3.client")
    @patch("document.services.storage.os.environ.get")
    def test_upload_file_to_s3_calls_boto_and_returns_url(
        self,
        mock_env,
        mock_boto_client,
    ):

        mock_env.return_value = "test-bucket"
        mock_s3 = mock_boto_client.return_value

        file = SimpleUploadedFile("test.txt", b"hello world")
        key = "documents/test.txt"

        url = upload_file_to_s3(file, key)

        mock_boto_client.assert_called_once_with("s3")
        mock_s3.upload_fileobj.assert_called_once_with(
            file,
            "test-bucket",
            key,
        )

        self.assertEqual(
            url,
            "https://test-bucket.s3.amazonaws.com/documents/test.txt",
        )
