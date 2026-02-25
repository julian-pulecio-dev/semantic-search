from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch
from document.services.ingestion import ingest_document
from document.models import Document

User = get_user_model()


class IngestionServiceTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@email.com", password="password123"
        )
        self.file = SimpleUploadedFile(
            "test.txt", b"hello world", content_type="text/plain"
        )

    @patch("document.services.ingestion.DocumentChunkProcessor")
    @patch("document.services.ingestion.upload_file_to_s3")
    def test_ingest_document_success(
        self,
        mock_upload,
        mock_processor_class,
    ):
        mock_upload.return_value = "https://fake-url.com/test.txt"

        mock_processor_instance = mock_processor_class.return_value
        mock_processor_instance.process.return_value = []

        document, _ = ingest_document(self.user, self.file)

        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(document.user, self.user)
        mock_upload.assert_called_once()
        mock_processor_class.assert_called_once_with(document)
        mock_processor_instance.process.assert_called_once()

    @patch("document.services.ingestion.delete_file_from_s3")
    @patch("document.services.ingestion.upload_file_to_s3")
    def test_ingest_document_upload_fails(
        self,
        mock_upload,
        mock_delete,
    ):
        mock_upload.side_effect = Exception("S3 failed")

        with self.assertRaises(Exception):
            ingest_document(self.user, self.file)

        self.assertEqual(Document.objects.count(), 0)
        mock_delete.assert_not_called()

    @patch("document.services.ingestion.delete_file_from_s3")
    @patch("document.services.ingestion.DocumentChunkProcessor")
    @patch("document.services.ingestion.upload_file_to_s3")
    def test_ingest_document_db_fails_deletes_s3(
        self,
        mock_upload,
        mock_processor_class,
        mock_delete,
    ):
        mock_upload.return_value = "https://fake-url.com/test.txt"
        mock_processor_class.side_effect = Exception("DB failure")

        with self.assertRaises(Exception):
            ingest_document(self.user, self.file)

        self.assertEqual(Document.objects.count(), 0)
        mock_delete.assert_called_once()

    @patch("document.services.ingestion.delete_file_from_s3")
    @patch("document.services.ingestion.DocumentChunkProcessor")
    @patch("document.services.ingestion.upload_file_to_s3")
    def test_ingest_document_chunk_processor_fails(
        self,
        mock_upload,
        mock_processor_class,
        mock_delete,
    ):
        mock_upload.return_value = "https://fake-url.com/test.txt"

        mock_processor_instance = mock_processor_class.return_value
        mock_processor_instance.process.side_effect = Exception("Chunk fail")

        with self.assertRaises(Exception):
            ingest_document(self.user, self.file)

        self.assertEqual(Document.objects.count(), 0)
        mock_delete.assert_called_once()

    @patch("document.services.ingestion.DocumentChunkProcessor")
    @patch("document.services.ingestion.upload_file_to_s3")
    def test_document_persisted_on_success(
        self,
        mock_upload,
        mock_processor_class,
    ):
        mock_upload.return_value = "https://fake-url.com/test.txt"
        mock_processor_class.return_value.process.return_value = []

        ingest_document(self.user, self.file)

        document = Document.objects.first()
        self.assertIsNotNone(document)
        self.assertEqual(document.user, self.user)
