from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from unittest.mock import patch

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
        """Verify that a POST request to create an upload session returns the
        expected response with a presigned URL and document ID."""

        mock_service.return_value = self.mock_response_data

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["document_id"], "some-uuid")
        self.assertEqual(response.data["url"], self.mock_response_data["url"])
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(response.data["expires_at"], "2024-01-01T00:00:00Z")
        mock_service.assert_called_once()

    def test_unauthenticated_request(self):
        """Verify that a POST request to create an upload session without
        authentication returns a 401 Unauthorized response."""

        self.client.force_authenticate(user=None)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
