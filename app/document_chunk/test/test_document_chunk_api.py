from unittest.mock import patch, MagicMock
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
            status=Document.Status.PROCESSED,
            s3_key="key.pdf",
        )

        self.other_document = Document.objects.create(
            user=self.other_user,
            status=Document.Status.PROCESSED,
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


class ChunkRefreshViewTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="refresh@test.com", password="password123"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSED,
            s3_key="docs/file.pdf",
        )
        self.chunk = DocumentChunk.objects.create(
            document=self.document,
            content="Original content",
            embedding=[0.0] * 1024,
            chunk_index=0,
            bounding_polygons=[
                {
                    "page_number": 1,
                    "points": [[0, 0], [100, 0], [100, 50], [0, 50]],
                }
            ],
        )
        self.url = reverse(
            "document-chunk-refresh", kwargs={"id": self.chunk.id}
        )
        self.valid_polygons = [
            {
                "page_number": 1,
                "points": [[10, 10], [200, 10], [200, 60], [10, 60]],
            }
        ]

    @patch("document_chunk.views.ChunkRefreshService")
    def test_refresh_updates_chunk_and_returns_200(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        refreshed_chunk = self.chunk
        refreshed_chunk.content = "New content from polygon"
        refreshed_chunk.embedding = [0.1] * 1024
        refreshed_chunk.bounding_polygons = self.valid_polygons
        mock_service.refresh.return_value = refreshed_chunk

        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            self.url,
            {"bounding_polygons": self.valid_polygons},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.chunk.id))
        mock_service.refresh.assert_called_once_with(
            chunk=self.chunk,
            bounding_polygons=self.valid_polygons,
        )

    @patch("document_chunk.views.ChunkRefreshService")
    def test_refresh_returns_400_when_polygons_empty(self, mock_service_cls):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            self.url,
            {"bounding_polygons": []},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_service_cls.return_value.refresh.assert_not_called()

    @patch("document_chunk.views.ChunkRefreshService")
    def test_refresh_returns_400_when_polygons_missing(self, mock_service_cls):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_service_cls.return_value.refresh.assert_not_called()

    def test_refresh_requires_authentication(self):
        response = self.client.patch(
            self.url,
            {"bounding_polygons": self.valid_polygons},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_returns_404_for_nonexistent_chunk(self):
        import uuid

        self.client.force_authenticate(user=self.user)
        url = reverse("document-chunk-refresh", kwargs={"id": uuid.uuid4()})

        response = self.client.patch(
            url,
            {"bounding_polygons": self.valid_polygons},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SemanticSearchViewTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="search@test.com", password="password123"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSED,
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
