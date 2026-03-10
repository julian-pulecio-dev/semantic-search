from unittest import mock
from django.test import TestCase
from django.contrib.auth import get_user_model
from document.models import Document
from upload_session.models import UploadSession
from upload_session.services.upload_session_service import UploadSessionService

User = get_user_model()


class UploadSessionServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com", password="password123"
        )
        self.mock_storage = mock.MagicMock()
        self.service = UploadSessionService(
            user=self.user, storage=self.mock_storage
        )

    def test_create_upload_session_success(self):
        fake_s3_key = "user/1/doc/abc/file.pdf"
        fake_presigned_data = {
            "url": "https://s3.amazon.com/bucket",
            "fields": {
                "key": fake_s3_key,
                "AWSAccessKeyId": "test-key",
                "policy": "test-policy",
                "signature": "test-signature",
            },
        }

        self.mock_storage.build_document_key.return_value = fake_s3_key
        self.mock_storage.generate_presigned_url_for_upload.return_value = (
            fake_presigned_data
        )

        result = self.service.create_upload_session()

        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(UploadSession.objects.count(), 1)

        _ = Document.objects.first()

        self.assertEqual(result["url"], fake_presigned_data)
        self.assertIsInstance(result["url"], dict)
        self.assertEqual(result["url"]["url"], "https://s3.amazon.com/bucket")
        self.assertEqual(result["url"]["fields"]["key"], fake_s3_key)

        self.mock_storage.generate_presigned_url_for_upload.assert_called_once_with(
            upload_session_id=UploadSession.objects.first().id,
            key=fake_s3_key,
            user_id=self.user.id,
        )

    def test_transaction_rollback_on_s3_failure(self):
        self.mock_storage.generate_presigned_url_for_upload.side_effect = (
            Exception("S3 Connection Error")
        )

        with self.assertRaises(Exception):
            self.service.create_upload_session()

        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(UploadSession.objects.count(), 0)
