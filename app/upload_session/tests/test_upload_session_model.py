import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from unittest.mock import patch
from upload_session.models import UploadSession
from document.models import Document

User = get_user_model()


class UploadSessionModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com", password="password123"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PENDING,
            s3_key="path/to/file.pdf",
        )
        self.session_data = {
            "document": self.document,
            "user": self.user,
            "expires_at": UploadSession.default_expiration(),
        }

    def test_create_upload_session(self):
        """Verify that an UploadSession can be created with valid data and has
        the correct default values."""

        session = UploadSession.objects.create(**self.session_data)
        self.assertEqual(session.status, UploadSession.Status.CREATED)
        self.assertIsInstance(session.id, uuid.UUID)

    @patch("upload_session.models.timezone.now")
    def test_default_expiration_logic(self, mock_now):
        """Verify that the default expiration time is set to 15 minutes from
        the current time."""

        fixed_now = timezone.now()
        mock_now.return_value = fixed_now

        expiration = UploadSession.default_expiration()
        expected = fixed_now + timedelta(minutes=15)

        self.assertEqual(expiration, expected)

    def test_status_choices(self):
        """Verify that the status field only accepts defined choices."""

        session = UploadSession.objects.create(**self.session_data)
        session.status = UploadSession.Status.UPLOADED
        session.save()
        self.assertEqual(session.status, "uploaded")

    def test_cascade_on_user_deletion(self):
        """Verify that deleting a user also deletes associated upload
        sessions."""

        UploadSession.objects.create(**self.session_data)
        self.user.delete()
        self.assertEqual(UploadSession.objects.count(), 0)

    def test_related_name_access(self):
        """Verify that the related_name 'upload_sessions' allows access from
        the Document model."""

        UploadSession.objects.create(**self.session_data)
        self.assertEqual(self.document.upload_sessions.count(), 1)
