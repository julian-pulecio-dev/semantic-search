import uuid
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from document.models import Document
from document_page.models import DocumentPage

User = get_user_model()


def PAGE_LIST_URL(doc_id):
    return reverse("document:page-list", kwargs={"doc_id": doc_id})


def PAGE_DETAIL_URL(doc_id, pk):
    return reverse("document:page-detail", kwargs={"doc_id": doc_id, "pk": pk})


class DocumentPageListCreateViewTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="user@test.com", password="password123"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSED,
            s3_key="key.pdf",
        )
        self.other_document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSED,
            s3_key="other.pdf",
        )
        self.page1 = DocumentPage.objects.create(document=self.document)
        self.page2 = DocumentPage.objects.create(document=self.document)
        self.other_page = DocumentPage.objects.create(
            document=self.other_document
        )

    def test_list_returns_pages_for_requested_document(self):
        response = self.client.get(PAGE_LIST_URL(self.document.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        returned_ids = {page["id"] for page in response.data}
        self.assertIn(str(self.page1.id), returned_ids)
        self.assertIn(str(self.page2.id), returned_ids)

    def test_list_does_not_return_pages_from_other_documents(self):
        response = self.client.get(PAGE_LIST_URL(self.document.id))

        returned_ids = {page["id"] for page in response.data}
        self.assertNotIn(str(self.other_page.id), returned_ids)

    def test_list_accessible_without_authentication(self):
        response = self.client.get(PAGE_LIST_URL(self.document.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_returns_empty_for_document_without_pages(self):
        empty_doc = Document.objects.create(
            user=self.user,
            status=Document.Status.PENDING,
            s3_key="empty.pdf",
        )
        response = self.client.get(PAGE_LIST_URL(empty_doc.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_create_page_for_document(self):
        response = self.client.post(PAGE_LIST_URL(self.document.id))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data["document"]), str(self.document.id))
        self.assertTrue(
            DocumentPage.objects.filter(id=response.data["id"]).exists()
        )

    def test_create_page_sets_document_from_url(self):
        response = self.client.post(PAGE_LIST_URL(self.document.id))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        page = DocumentPage.objects.get(id=response.data["id"])
        self.assertEqual(page.document_id, self.document.id)

    def test_list_returns_404_for_nonexistent_document(self):
        response = self.client.get(PAGE_LIST_URL(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)


class DocumentPageRetrieveUpdateDestroyViewTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="user@test.com", password="password123"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSED,
            s3_key="key.pdf",
        )
        self.page = DocumentPage.objects.create(document=self.document)

    def test_retrieve_returns_page(self):
        response = self.client.get(
            PAGE_DETAIL_URL(self.document.id, self.page.id)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["id"]), str(self.page.id))
        self.assertEqual(str(response.data["document"]), str(self.document.id))

    def test_retrieve_accessible_without_authentication(self):
        response = self.client.get(
            PAGE_DETAIL_URL(self.document.id, self.page.id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_returns_404_for_nonexistent_page(self):
        response = self.client.get(
            PAGE_DETAIL_URL(self.document.id, uuid.uuid4())
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_returns_404_for_page_from_different_document(self):
        other_document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSED,
            s3_key="other.pdf",
        )
        response = self.client.get(
            PAGE_DETAIL_URL(other_document.id, self.page.id)
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_removes_page(self):
        response = self.client.delete(
            PAGE_DETAIL_URL(self.document.id, self.page.id)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DocumentPage.objects.filter(id=self.page.id).exists())
