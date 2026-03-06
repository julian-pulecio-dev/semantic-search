from django.test import TestCase
from django.db.utils import IntegrityError
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from document.models import Document
import uuid

User = get_user_model()


class DocumentModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser", password="password123"
        )

    def test_document_creation(self):
        """Validate that a Document can be created with valid data."""

        doc = Document.objects.create(
            status=Document.Status.READY, user=self.user
        )
        self.assertTrue(isinstance(doc.id, uuid.UUID))
        self.assertEqual(doc.status, Document.Status.READY)
        self.assertEqual(doc.user, self.user)
        self.assertIsNotNone(doc.uploaded_at)

    def test_document_str_method(self):
        doc = Document.objects.create(
            status=Document.Status.PENDING, user=self.user
        )
        self.assertEqual(str(doc), str(doc.id))

    def test_s3_key_uniqueness(self):
        """Ensure that the s3_key field is unique across Document instances."""

        s3_key = "path/to/my/file.pdf"
        Document.objects.create(
            s3_key=s3_key, status=Document.Status.PROCESSING, user=self.user
        )

        with self.assertRaises(IntegrityError):
            Document.objects.create(
                s3_key=s3_key, status=Document.Status.READY, user=self.user
            )

    def test_cascade_deletion(self):
        """Verify that deleting a User also deletes associated Document instances."""

        Document.objects.create(status=Document.Status.PENDING, user=self.user)
        self.assertEqual(Document.objects.count(), 1)

        self.user.delete()
        self.assertEqual(Document.objects.count(), 0)

    def test_invalid_status_choice(self):
        """Validate that Django raises a ValidationError for invalid status choices."""

        doc = Document(status="INVALID_STATUS", user=self.user)
        with self.assertRaises(ValidationError):
            doc.full_clean()
