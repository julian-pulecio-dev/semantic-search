from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from document.models import Document
from document_chunk.models import DocumentChunk

User = get_user_model()


class DocumentChunkViewsTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="user@test.com", password="password123"
        )

        self.other_user = User.objects.create_user(
            email="other@test.com", password="password123"
        )

        self.document = Document.objects.create(
            user=self.user,
            url="http://test.com/file.pdf",
            s3_key="key.pdf",
        )

        self.other_document = Document.objects.create(
            user=self.other_user,
            url="http://test.com/file2.pdf",
            s3_key="key2.pdf",
        )

        self.chunk1 = DocumentChunk.objects.create(
            document=self.document,
            content="Chunk 1 content",
            embedding=[0.0] * 1024,
            chunk_index=0,
        )

        self.chunk2 = DocumentChunk.objects.create(
            document=self.document,
            content="Chunk 2 content",
            embedding=[0.0] * 1024,
            chunk_index=1,
        )

        self.other_chunk = DocumentChunk.objects.create(
            document=self.other_document,
            content="Other user chunk",
            embedding=[0.0] * 1024,
            chunk_index=0,
        )

    def test_list_document_chunks_returns_user_chunks(self):
        self.client.force_authenticate(user=self.user)

        url = reverse(
            "document-chunk-list",
            kwargs={"document_id": self.document.id},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        returned_ids = {chunk["id"] for chunk in response.data}
        self.assertIn(str(self.chunk1.id), returned_ids)
        self.assertIn(str(self.chunk2.id), returned_ids)

    def test_list_document_chunks_returns_empty_for_other_users_document(self):
        self.client.force_authenticate(user=self.user)

        url = reverse(
            "document-chunk-list",
            kwargs={"document_id": self.other_document.id},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_list_document_chunks_requires_authentication(self):
        url = reverse(
            "document-chunk-list",
            kwargs={"document_id": self.document.id},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_chunk_returns_chunk(self):
        self.client.force_authenticate(user=self.user)

        url = reverse(
            "document-chunk-detail",
            kwargs={"id": self.chunk1.id},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.chunk1.id))
        self.assertEqual(response.data["content"], self.chunk1.content)

    def test_retrieve_chunk_returns_404_if_not_owner(self):
        self.client.force_authenticate(user=self.user)

        url = reverse(
            "document-chunk-detail",
            kwargs={"id": self.other_chunk.id},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_chunk_requires_authentication(self):
        url = reverse(
            "document-chunk-detail",
            kwargs={"id": self.chunk1.id},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SemanticSearchViewTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="search@test.com", password="password123"
        )
        self.document = Document.objects.create(
            user=self.user,
            url="http://test.com/file.pdf",
            s3_key="search-key.pdf",
        )
        self.embedding = [0.1] * 1024
        self.url = reverse("semantic-search")

        self.chunk_with_embedding = DocumentChunk.objects.create(
            document=self.document,
            content="Chunk with embedding",
            embedding=self.embedding,
            chunk_index=0,
        )
        self.chunk_without_embedding = DocumentChunk.objects.create(
            document=self.document,
            content="Chunk without embedding",
            embedding=None,
            chunk_index=1,
        )

    @patch("document_chunk.views.EmbeddingsProcessor")
    def test_search_excludes_chunks_with_null_embedding(
        self, mock_processor_cls
    ):
        mock_processor_cls.return_value.get_embedding.return_value = (
            self.embedding
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url, {"query": "test", "top_k": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {chunk["id"] for chunk in response.data}
        self.assertNotIn(str(self.chunk_without_embedding.id), returned_ids)

    @patch("document_chunk.views.EmbeddingsProcessor")
    def test_search_returns_chunks_with_embedding(self, mock_processor_cls):
        mock_processor_cls.return_value.get_embedding.return_value = (
            self.embedding
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url, {"query": "test", "top_k": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {chunk["id"] for chunk in response.data}
        self.assertIn(str(self.chunk_with_embedding.id), returned_ids)

    def test_search_requires_authentication(self):
        response = self.client.post(self.url, {"query": "test", "top_k": 5})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
