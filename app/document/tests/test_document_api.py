from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from document.models import Document

User = get_user_model()

LIST_URL = reverse("document:document-list")


def DETAIL_URL(pk):
    return reverse("document:document-detail", kwargs={"pk": pk})


class DocumentListCreateViewTestCase(APITestCase):

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email="admin@test.com", password="adminpassword"
        )
        self.regular_user = User.objects.create_user(
            email="user1@test.com", password="userpassword"
        )
        self.doc1 = Document.objects.create(
            status=Document.Status.PROCESSED,
            user=self.regular_user,
            s3_key="key1",
        )
        self.doc2 = Document.objects.create(
            status=Document.Status.PENDING,
            user=self.regular_user,
            s3_key="key2",
        )

    def test_list_requires_authentication(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_only_own_documents(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_list_does_not_return_other_users_documents(self):
        Document.objects.create(
            status=Document.Status.PROCESSED,
            user=self.admin_user,
            s3_key="admin_key",
        )
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)


class DocumentRetrieveUpdateDestroyViewTestCase(APITestCase):

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email="admin@test.com", password="adminpassword"
        )
        self.regular_user = User.objects.create_user(
            email="user1@test.com", password="userpassword"
        )
        self.doc = Document.objects.create(
            status=Document.Status.PROCESSED,
            user=self.admin_user,
            s3_key="key1",
        )

    def test_retrieve_returns_document(self):
        response = self.client.get(DETAIL_URL(self.doc.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["id"]), str(self.doc.id))

    def test_retrieve_accessible_without_authentication(self):
        response = self.client.get(DETAIL_URL(self.doc.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_returns_404_for_nonexistent_document(self):
        import uuid

        response = self.client.get(DETAIL_URL(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_status_is_read_only_on_put(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.put(
            DETAIL_URL(self.doc.id),
            {"status": Document.Status.FAILED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, Document.Status.PROCESSED)

    def test_status_is_read_only_on_patch(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.patch(
            DETAIL_URL(self.doc.id),
            {"status": Document.Status.PROCESSING},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, Document.Status.PROCESSED)

    @patch("document.views.S3FileLoaderService.delete_file")
    def test_delete_requires_admin(self, mock_delete):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.delete(DETAIL_URL(self.doc.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Document.objects.filter(id=self.doc.id).exists())

    @patch("document.views.S3FileLoaderService.delete_file")
    def test_delete_by_admin_removes_document_and_s3_file(self, mock_delete):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(DETAIL_URL(self.doc.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.doc.id).exists())
        mock_delete.assert_called_once_with(key=self.doc.s3_key)
