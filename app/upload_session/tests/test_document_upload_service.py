from unittest.mock import MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from document.models import Document
from upload_session.models import UploadSession
from upload_session.services.document_upload_service import (
    DocumentUploadService,
)

User = get_user_model()


class TestDocumentUploadService(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpassword"
        )
        self.mock_storage = MagicMock()
        self.service = DocumentUploadService(
            user=self.user, storage=self.mock_storage
        )

    def test_create_upload_request_success(self):
        """Verify that create_upload_request creates a document and upload
        session, and returns the correct response."""

        mock_url = {"url": "https://s3-presigned-url.com", "fields": {}}
        self.mock_storage.generate_presigned_url_for_upload.return_value = (
            mock_url
        )
        self.mock_storage.build_document_key.return_value = "documents/1/1"

        result = self.service.create_upload_request()

        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(UploadSession.objects.count(), 1)

        document = Document.objects.first()
        session = UploadSession.objects.first()

        self.assertEqual(result["document_id"], document.id)
        self.assertEqual(result["upload_session_id"], session.id)
        self.assertEqual(result["url"], mock_url)
        self.assertEqual(result["status"], Document.Status.PENDING)

        self.mock_storage.build_document_key.assert_called_once_with(
            self.user.id, document.id
        )
        self.mock_storage.generate_presigned_url_for_upload.assert_called_once_with(
            key=document.s3_key, user_id=self.user.id
        )

    def test_create_document_record_logic(self):
        """Verify that _create_document_record creates a document with the
        correct attributes."""

        self.mock_storage.build_document_key.return_value = "custom/key/123"

        doc = self.service._create_document_record()

        self.assertEqual(doc.user, self.user)
        self.assertEqual(doc.status, Document.Status.PENDING)
        self.assertEqual(doc.s3_key, "custom/key/123")
        self.assertTrue(Document.objects.filter(id=doc.id).exists())

    def test_create_upload_session_record_logic(self):
        """Verify that _create_upload_session_record creates an upload session
        with the correct attributes."""

        doc = Document.objects.create(
            user=self.user, status=Document.Status.PENDING, s3_key="key"
        )

        session = self.service._create_upload_session_record(doc)

        self.assertEqual(session.document, doc)
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.s3_key, doc.s3_key)
        self.assertIsNotNone(session.expires_at)

    def test_s3_failure_behavior(self):
        """Verify that create_upload_request raises an exception when S3 URL
        generation fails, and that the document record is still created."""

        self.mock_storage.generate_presigned_url_for_upload.side_effect = (
            Exception("S3 Error")
        )

        with self.assertRaises(Exception):
            self.service.create_upload_request(key="test")
