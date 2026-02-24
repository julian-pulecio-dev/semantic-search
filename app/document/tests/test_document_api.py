from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from unittest.mock import patch

CREATE_DOCUMENT_URL = reverse("document:create")
LIST_DOCUMENTS_URL = reverse("document:list_all")
LIST_USER_DOCUMENTS_URL = reverse("document:list_user")


def create_user(**params):
    return get_user_model().objects.create_user(**params)


def create_superuser(**params):
    return get_user_model().objects.create_superuser(**params)


def create_document(
    user,
    url="https://bucket.s3.amazonaws.com/documents/test.txt",
    s3_key="test.txt",
):
    return user.documents.create(url=url, s3_key=s3_key)


class DocumentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_user(
            email="test_user@email.com", password="user_password123*"
        )
        self.superuser = create_superuser(
            email="admin_user@email.com", password="admin_password123*"
        )
        self.other_user = create_user(
            email="other_user@email.com", password="other_user_password123*"
        )
        self.client.force_authenticate(user=self.user)

    @patch("document.views.DocumentChunkProcessor")  # <--- AÑADE ESTO
    @patch("document.views.uuid4")
    @patch("document.views.upload_file_to_s3")
    def test_create_document_success(
        self, mock_upload, mock_uuid4, mock_processor
    ):
        mock_uuid4.return_value = "1234-5678-9012"
        mock_upload.return_value = "https://fake-url.com/test.txt"
        mock_processor.return_value.process.return_value = []

        file = SimpleUploadedFile(
            "test.txt", b"hello world", content_type="text/plain"
        )

        response = self.client.post(
            CREATE_DOCUMENT_URL, {"file": file}, format="multipart"
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("url", response.data)
        self.assertEqual(self.user.documents.count(), 1)

        mock_processor.assert_called_once()

    @patch("document.views.delete_file_from_s3")
    def test_delete_document_success(self, mock_delete):
        create_document(self.user)
        document_id = self.user.documents.first().id
        mock_delete.return_value = True

        self.assertEqual(self.user.documents.count(), 1)

        response = self.client.delete(
            reverse("document:delete", kwargs={"pk": document_id})
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.user.documents.count(), 0)
        mock_delete.assert_called_once()

    def test_delete_document_not_found(self):
        response = self.client.delete(
            reverse(
                "document:delete",
                kwargs={"pk": "00000000-0000-0000-0000-000000000000"},
            )
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.user.documents.count(), 0)

    def test_delete_document_not_owned(self):

        create_document(self.other_user)
        document_id = self.other_user.documents.first().id

        response = self.client.delete(
            reverse("document:delete", kwargs={"pk": document_id})
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.other_user.documents.count(), 1)
        self.assertEqual(self.user.documents.count(), 0)

    def test_list_all_documents_as_admin(self):
        self.client.force_authenticate(user=self.superuser)
        document = create_document(self.user)
        response = self.client.get(LIST_DOCUMENTS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["url"], document.url)

    def test_list_all_documents_as_non_admin(self):
        response = self.client.get(LIST_DOCUMENTS_URL)
        self.assertEqual(response.status_code, 403)

    def test_list_user_documents(self):
        document = create_document(self.user)
        response = self.client.get(LIST_USER_DOCUMENTS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["url"], document.url)

    def test_list_user_documents_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(LIST_USER_DOCUMENTS_URL)
        self.assertEqual(response.status_code, 401)

    def test_list_other_user_documents(self):
        create_document(self.other_user)
        response = self.client.get(LIST_USER_DOCUMENTS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)

    def retrieve_document_success(self):
        document = create_document(self.user)
        response = self.client.get(
            reverse("document:retrieve", kwargs={"pk": document.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["url"], document.url)
        self.assertEqual(response.data["s3_key"], document.s3_key)

    def retrieve_document_not_found(self):
        response = self.client.get(
            reverse(
                "document:retrieve",
                kwargs={"pk": "00000000-0000-0000-0000-000000000000"},
            )
        )
        self.assertEqual(response.status_code, 404)

    def retrieve_document_not_owned(self):
        document = create_document(self.other_user)
        response = self.client.get(
            reverse("document:retrieve", kwargs={"pk": document.id})
        )
        self.assertEqual(response.status_code, 404)

    @patch("document.views.DocumentChunkProcessor")
    @patch("document.views.uuid4")
    @patch("document.views.upload_file_to_s3")
    def test_create_document_calls_process_document(
        self,
        mock_upload,
        mock_uuid4,
        mock_processor_class,
    ):
        mock_uuid4.return_value = "1234-5678"
        mock_upload.return_value = "https://fake-url.com/test.txt"

        mock_instance = mock_processor_class.return_value
        mock_instance.process.return_value = [
            {"content": "chunk 1", "page_number": 1, "document_id": 1}
        ]

        file = SimpleUploadedFile(
            "test.txt", b"hello world", content_type="text/plain"
        )
        response = self.client.post(
            CREATE_DOCUMENT_URL, {"file": file}, format="multipart"
        )
        self.assertEqual(response.status_code, 201)

        document = self.user.documents.first()
        mock_processor_class.assert_called_once_with(document)
        mock_instance.process.assert_called_once()
