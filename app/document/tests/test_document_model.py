from django.test import TestCase
from django.db.utils import IntegrityError
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.contrib.auth import get_user_model
from document.models import Document
from document_type.models import DocumentType
import uuid

User = get_user_model()


class DocumentModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser", password="password123"
        )

        self.document_type = DocumentType.objects.create(name="Invoice")

    def test_document_creation(self):
        """Validate that a Document can be created with valid data."""

        doc = Document.objects.create(
            status=Document.Status.PROCESSED,
            user=self.user,
            document_type=self.document_type,
        )

        self.assertTrue(isinstance(doc.id, uuid.UUID))
        self.assertEqual(doc.status, Document.Status.PROCESSED)
        self.assertEqual(doc.user, self.user)
        self.assertEqual(doc.document_type, self.document_type)
        self.assertIsNotNone(doc.uploaded_at)

    def test_document_str_method(self):
        doc = Document.objects.create(
            status=Document.Status.PENDING,
            user=self.user,
            document_type=self.document_type,
        )
        self.assertEqual(str(doc), str(doc.id))

    def test_s3_key_uniqueness(self):
        """Ensure that the s3_key field is unique across Document instances."""

        s3_key = "path/to/my/file.pdf"

        Document.objects.create(
            s3_key=s3_key,
            status=Document.Status.PROCESSING,
            user=self.user,
            document_type=self.document_type,
        )

        with self.assertRaises(IntegrityError):
            Document.objects.create(
                s3_key=s3_key,
                status=Document.Status.PROCESSED,
                user=self.user,
                document_type=self.document_type,
            )

    def test_cascade_deletion(self):
        """Verify that deleting a User also deletes associated Document
        instances."""

        Document.objects.create(
            status=Document.Status.PENDING,
            user=self.user,
            document_type=self.document_type,
        )

        self.assertEqual(Document.objects.count(), 1)

        self.user.delete()

        self.assertEqual(Document.objects.count(), 0)

    def test_invalid_status_choice(self):
        """Validate that Django raises a ValidationError for invalid status
        choices."""

        doc = Document(
            status="INVALID_STATUS",
            user=self.user,
            document_type=self.document_type,
        )

        with self.assertRaises(ValidationError):
            doc.full_clean()

    def test_document_type_protect_on_delete(self):
        """Ensure deleting a DocumentType referenced by a Document raises
        ProtectedError."""

        _ = Document.objects.create(
            status=Document.Status.PROCESSED,
            user=self.user,
            document_type=self.document_type,
        )

        with self.assertRaises(ProtectedError):
            self.document_type.delete()

    def test_document_creation_without_document_type(self):
        """document_type is required at the DB level; omitting it raises an error."""

        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Document.objects.create(
                status=Document.Status.PENDING,
                user=self.user,
            )
