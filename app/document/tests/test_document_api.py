from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from document.models import Document
from document_type.models import DocumentType

User = get_user_model()

LIST_ALL_URL = reverse("document:list_all")
LIST_USER_URL = reverse("document:list_user")


def RETRIEVE_URL(pk):
    return reverse("document:retrieve", kwargs={"pk": pk})


def DELETE_URL(pk):
    return reverse("document:delete", kwargs={"pk": pk})


class DocumentViewsTestCase(APITestCase):

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email="admin@test.com", password="adminpassword"
        )

        self.regular_user = User.objects.create_user(
            email="user1@test.com", password="userpassword"
        )

        self.other_user = User.objects.create_user(
            email="user2@test.com", password="userpassword"
        )

        self.document_type = DocumentType.objects.create(name="Invoice")

        self.doc1 = Document.objects.create(
            status=Document.Status.READY,
            user=self.regular_user,
            s3_key="key1",
            document_type=self.document_type,
        )

        self.doc2 = Document.objects.create(
            status=Document.Status.PENDING,
            user=self.other_user,
            s3_key="key2",
            document_type=self.document_type,
        )

    def test_list_all_documents_admin_only(self):
        """Validate that only admin users can access the list of all
        documents."""

        url = LIST_ALL_URL

        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # verify document_type exists in response
        self.assertIn("document_type", response.data[0])

    def test_list_user_documents(self):
        """Validate that users can only see their own documents."""

        url = LIST_USER_URL
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(str(response.data[0]["id"]), str(self.doc1.id))
        self.assertEqual(
            response.data[0]["document_type"], self.document_type.id
        )

    def test_retrieve_document_permissions(self):
        """Validate that users can only retrieve documents they own."""

        url = RETRIEVE_URL(self.doc2.id)

        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["id"]), str(self.doc2.id))
        self.assertEqual(response.data["document_type"], self.document_type.id)

    @patch("document.views.S3FileLoaderService.delete_file")
    def test_delete_document_and_s3_call(self, mock_delete):
        """Validate that deleting a document also triggers the S3 file
        deletion."""

        url = DELETE_URL(self.doc1.id)
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.doc1.id).exists())
        mock_delete.assert_called_once_with(key=self.doc1.s3_key)

    def test_delete_other_user_document_fails(self):
        """Validate that users cannot delete documents they do not own."""

        url = DELETE_URL(self.doc2.id)
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Document.objects.filter(id=self.doc2.id).exists())
