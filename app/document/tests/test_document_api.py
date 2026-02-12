from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from unittest.mock import patch

CREATE_DOCUMENT_URL = reverse("document:create")


def create_user(**params):
    return get_user_model().objects.create_user(**params)


class DocumentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_user(
            email="test_user@email.com", password="user_password123*"
        )
        self.client.force_authenticate(user=self.user)

    @patch("document.services.storage.upload_file_to_s3")
    def test_create_document_success(self, mock_boto_client):
        mock_s3 = mock_boto_client.return_value

        file = SimpleUploadedFile(
            "test.txt", b"hello world", content_type="text/plain"
        )

        response = self.client.post(
            CREATE_DOCUMENT_URL, {"file": file}, format="multipart"
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("url", response.data)
        self.assertEqual(self.user.documents.count(), 1)
