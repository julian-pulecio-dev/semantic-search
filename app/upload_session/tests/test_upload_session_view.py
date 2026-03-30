import uuid
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from unittest.mock import patch
from upload_session.models import UploadSession
from document.models import Document
from document_type.models import DocumentType

User = get_user_model()

CREATE_UPLOAD_SESSION_URL = reverse("upload_session:create")


class CreateUploadSessionViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com", password="password123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = CREATE_UPLOAD_SESSION_URL

        self.document_type = DocumentType.objects.create(name="Invoice")

        self.mock_response_data = {
            "document_id": "some-uuid",
            "url": {
                "url": "https://s3-presigned-url.com",
                "fields": {
                    "AWSAccessKeyId": "test-key",
                    "policy": "test-policy",
                    "signature": "test-signature",
                },
            },
            "status": "PENDING",
            "expires_at": "2024-01-01T00:00:00Z",
        }

    @patch("upload_session.views.DocumentUploadService.create_upload_request")
    def test_create_upload_session_success(self, mock_service):
        """Verify that a POST request with a valid document_type_id returns
        the expected response with a presigned URL and document ID."""

        mock_service.return_value = self.mock_response_data

        response = self.client.post(
            self.url,
            {"document_type_id": self.document_type.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["document_id"], "some-uuid")
        self.assertEqual(response.data["url"], self.mock_response_data["url"])
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(response.data["expires_at"], "2024-01-01T00:00:00Z")
        mock_service.assert_called_once()

    def test_missing_document_type_id_returns_400(self):
        """Verify that a POST request without document_type_id returns 400."""

        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_type_id", response.data)

    def test_invalid_document_type_id_returns_400(self):
        """Verify that a POST request with a non-existent document_type_id
        returns 400."""

        response = self.client.post(
            self.url, {"document_type_id": str(uuid.uuid4())}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_type_id", response.data)

    def test_unauthenticated_request(self):
        """Verify that a POST request without authentication returns 401."""

        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url,
            {"document_type_id": str(self.document_type.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UploadSessionDetailViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="statususer@example.com", password="password123"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="password123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.document_type = DocumentType.objects.create(name="Contract")

        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PENDING,
            document_type=self.document_type,
            s3_key="docs/file.pdf",
        )
        self.session = UploadSession.objects.create(
            user=self.user,
            document=self.document,
            expires_at=UploadSession.default_expiration(),
        )

    def _url(self, session_id):
        return reverse("upload_session:detail", kwargs={"id": session_id})

    def test_returns_session_status(self):
        response = self.client.get(self._url(self.session.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["id"]), str(self.session.id))
        self.assertEqual(response.data["status"], UploadSession.Status.CREATED)
        self.assertIn("expires_at", response.data)
        self.assertIn("created_at", response.data)

    def test_returns_document_details(self):
        """Verify that the session detail response includes the nested
        document object with all expected fields."""

        response = self.client.get(self._url(self.session.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        document_data = response.data["document"]
        self.assertEqual(str(document_data["id"]), str(self.document.id))
        self.assertEqual(document_data["status"], Document.Status.PENDING)
        self.assertEqual(document_data["s3_key"], "docs/file.pdf")
        self.assertEqual(
            str(document_data["document_type"]), str(self.document_type.id)
        )

    def test_returns_404_for_other_users_session(self):
        other_document = Document.objects.create(
            user=self.other_user,
            status=Document.Status.PENDING,
            document_type=self.document_type,
            s3_key="docs/other.pdf",
        )
        other_session = UploadSession.objects.create(
            user=self.other_user,
            document=other_document,
            expires_at=UploadSession.default_expiration(),
        )

        response = self.client.get(self._url(other_session.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_404_for_nonexistent_session(self):
        response = self.client.get(self._url(uuid.uuid4()))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self._url(self.session.id))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
