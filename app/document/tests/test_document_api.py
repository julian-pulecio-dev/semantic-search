from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from document.models import Document

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

        self.doc1 = Document.objects.create(
            status=Document.Status.PROCESSED,
            user=self.admin_user,
            s3_key="key1",
        )

        self.doc2 = Document.objects.create(
            status=Document.Status.PENDING,
            user=self.admin_user,
            s3_key="key2",
        )

    def test_list_all_documents_authenticated(self):
        """Validate that any authenticated user can list all documents."""

        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(LIST_ALL_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_list_all_documents_unauthenticated(self):
        """Validate that unauthenticated requests are rejected."""

        response = self.client.get(LIST_ALL_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_user_documents_returns_all(self):
        """Validate that list_user returns all documents (no ownership filter)."""

        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(LIST_USER_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_document_any_authenticated_user(self):
        """Validate that any authenticated user can retrieve any document."""

        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(RETRIEVE_URL(self.doc2.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["id"]), str(self.doc2.id))

    def test_retrieve_document_unauthenticated(self):
        """Validate that unauthenticated requests are rejected."""

        response = self.client.get(RETRIEVE_URL(self.doc1.id))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("document.views.S3FileLoaderService.delete_file")
    def test_delete_document_admin_only(self, mock_delete):
        """Validate that only admin users can delete documents."""

        url = DELETE_URL(self.doc1.id)

        self.client.force_authenticate(user=self.regular_user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Document.objects.filter(id=self.doc1.id).exists())

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.doc1.id).exists())
        mock_delete.assert_called_once_with(key=self.doc1.s3_key)
