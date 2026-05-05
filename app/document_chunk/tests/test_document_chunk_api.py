import uuid
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from document.models import Document
from document_page.models import DocumentPage
from document_chunk.models import DocumentChunk

User = get_user_model()


def CHUNK_LIST_URL(doc_id):
    return reverse("document:chunk-list", kwargs={"doc_id": doc_id})


def CHUNK_DETAIL_URL(doc_id, pk):
    return reverse(
        "document:chunk-detail", kwargs={"doc_id": doc_id, "pk": pk}
    )


def CHUNK_REFRESH_URL(doc_id, pk):
    return reverse(
        "document:chunk-refresh", kwargs={"doc_id": doc_id, "pk": pk}
    )


SEARCH_URL = reverse("semantic-search")


class DocumentChunkListCreateViewTestCase(APITestCase):

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
        self.page = DocumentPage.objects.create(document=self.document)

        self.other_document = Document.objects.create(
            user=self.other_user,
            status=Document.Status.PROCESSED,
            s3_key="key2.pdf",
        )
        self.other_page = DocumentPage.objects.create(
            document=self.other_document
        )

        self.chunk1 = DocumentChunk.objects.create(
            document=self.document,
            start_page=self.page,
            end_page=self.page,
            content="Chunk 1 content",
            embedding=[0.0] * 1024,
            chunk_index=0,
        )
        self.chunk2 = DocumentChunk.objects.create(
            document=self.document,
            start_page=self.page,
            end_page=self.page,
            content="Chunk 2 content",
            embedding=[0.0] * 1024,
            chunk_index=1,
        )
        self.other_chunk = DocumentChunk.objects.create(
            document=self.other_document,
            start_page=self.other_page,
            end_page=self.other_page,
            content="Other user chunk",
            embedding=[0.0] * 1024,
            chunk_index=0,
        )

    def test_list_returns_chunks_for_requested_page(self):
        url = CHUNK_LIST_URL(self.document.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        returned_ids = {chunk["id"] for chunk in response.data}
        self.assertIn(str(self.chunk1.id), returned_ids)
        self.assertIn(str(self.chunk2.id), returned_ids)

    def test_list_does_not_return_chunks_from_other_pages(self):
        url = CHUNK_LIST_URL(self.other_document.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {chunk["id"] for chunk in response.data}
        self.assertIn(str(self.other_chunk.id), returned_ids)
        self.assertNotIn(str(self.chunk1.id), returned_ids)

    def test_list_accessible_without_authentication(self):
        url = CHUNK_LIST_URL(self.document.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_returns_chunks_ordered_by_chunk_index(self):
        url = CHUNK_LIST_URL(self.document.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        indexes = [chunk["chunk_index"] for chunk in response.data]
        self.assertEqual(indexes, sorted(indexes))


class DocumentChunkRetrieveViewTestCase(APITestCase):

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
        self.chunk = DocumentChunk.objects.create(
            document=self.document,
            start_page=self.page,
            end_page=self.page,
            content="Chunk content",
            embedding=[0.0] * 1024,
            chunk_index=0,
        )

    def test_retrieve_returns_chunk(self):
        url = CHUNK_DETAIL_URL(self.document.id, self.chunk.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.chunk.id))
        self.assertEqual(response.data["content"], self.chunk.content)

    def test_retrieve_accessible_without_authentication(self):
        url = CHUNK_DETAIL_URL(self.document.id, self.chunk.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_returns_404_for_nonexistent_chunk(self):
        url = CHUNK_DETAIL_URL(self.document.id, uuid.uuid4())
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_returns_404_for_chunk_from_different_page(self):
        other_document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSED,
            s3_key="other.pdf",
        )
        _ = DocumentPage.objects.create(document=other_document)
        url = CHUNK_DETAIL_URL(other_document.id, self.chunk.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


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
        self.page = DocumentPage.objects.create(document=self.document)
        self.chunk = DocumentChunk.objects.create(
            document=self.document,
            start_page=self.page,
            end_page=self.page,
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
        url = CHUNK_REFRESH_URL(self.document.id, self.chunk.id)
        response = self.client.patch(
            url, {"bounding_polygons": self.valid_polygons}, format="json"
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
        url = CHUNK_REFRESH_URL(self.document.id, self.chunk.id)
        response = self.client.patch(
            url, {"bounding_polygons": []}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_service_cls.return_value.refresh.assert_not_called()

    @patch("document_chunk.views.ChunkRefreshService")
    def test_refresh_returns_400_when_polygons_missing(self, mock_service_cls):
        self.client.force_authenticate(user=self.user)
        url = CHUNK_REFRESH_URL(self.document.id, self.chunk.id)
        response = self.client.patch(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_service_cls.return_value.refresh.assert_not_called()

    def test_refresh_requires_authentication(self):
        url = CHUNK_REFRESH_URL(self.document.id, self.chunk.id)
        response = self.client.patch(
            url, {"bounding_polygons": self.valid_polygons}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_returns_404_for_nonexistent_chunk(self):
        self.client.force_authenticate(user=self.user)
        url = CHUNK_REFRESH_URL(self.document.id, uuid.uuid4())
        response = self.client.patch(
            url, {"bounding_polygons": self.valid_polygons}, format="json"
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
        self.page = DocumentPage.objects.create(document=self.document)
        self.embedding = [0.1] * 1024

        self.chunk_with_embedding = DocumentChunk.objects.create(
            document=self.document,
            start_page=self.page,
            end_page=self.page,
            content="Chunk with embedding",
            embedding=self.embedding,
            chunk_index=0,
        )
        self.chunk_without_embedding = DocumentChunk.objects.create(
            document=self.document,
            start_page=self.page,
            end_page=self.page,
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

        response = self.client.post(SEARCH_URL, {"query": "test"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {chunk["id"] for chunk in response.data}
        self.assertNotIn(str(self.chunk_without_embedding.id), returned_ids)

    @patch("document_chunk.views.EmbeddingsProcessor")
    def test_search_returns_chunk_with_embedding(self, mock_processor_cls):
        mock_processor_cls.return_value.get_embedding.return_value = (
            self.embedding
        )

        response = self.client.post(SEARCH_URL, {"query": "test"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {chunk["id"] for chunk in response.data}
        self.assertIn(str(self.chunk_with_embedding.id), returned_ids)

    @patch("document_chunk.views.EmbeddingsProcessor")
    def test_search_respects_k_parameter(self, mock_processor_cls):
        mock_processor_cls.return_value.get_embedding.return_value = (
            self.embedding
        )

        response = self.client.post(SEARCH_URL, {"query": "test", "k": 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data), 1)

    def test_search_rejects_k_above_max(self):
        response = self.client.post(SEARCH_URL, {"query": "test", "k": 101})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_search_rejects_k_below_min(self):
        response = self.client.post(SEARCH_URL, {"query": "test", "k": 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("document_chunk.views.EmbeddingsProcessor")
    def test_search_uses_default_k_when_not_provided(self, mock_processor_cls):
        mock_processor_cls.return_value.get_embedding.return_value = (
            self.embedding
        )

        response = self.client.post(SEARCH_URL, {"query": "test"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("document_chunk.views.EmbeddingsProcessor")
    def test_search_accessible_without_authentication(
        self, mock_processor_cls
    ):
        mock_processor_cls.return_value.get_embedding.return_value = (
            self.embedding
        )

        response = self.client.post(SEARCH_URL, {"query": "test"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {chunk["id"] for chunk in response.data}
        self.assertIn(str(self.chunk_with_embedding.id), returned_ids)

    @patch("document_chunk.views.EmbeddingsProcessor")
    def test_search_returns_chunks_across_all_documents(
        self, mock_processor_cls
    ):
        mock_processor_cls.return_value.get_embedding.return_value = (
            self.embedding
        )

        other_user = User.objects.create_user(
            email="other@test.com", password="password123"
        )
        other_document = Document.objects.create(
            user=other_user,
            status=Document.Status.PROCESSED,
            s3_key="other-key.pdf",
        )
        other_page = DocumentPage.objects.create(document=other_document)
        other_chunk = DocumentChunk.objects.create(
            document=other_document,
            start_page=other_page,
            end_page=other_page,
            content="Other user chunk",
            embedding=self.embedding,
            chunk_index=0,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(SEARCH_URL, {"query": "test", "k": 100})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {chunk["id"] for chunk in response.data}
        self.assertIn(str(self.chunk_with_embedding.id), returned_ids)
        self.assertIn(str(other_chunk.id), returned_ids)
