from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model

from document.models import Document
from document_chunk.models import DocumentChunk
from document_page.models import DocumentPage
from document_chunk.services.chunk_refresh_service import ChunkRefreshService
from document_chunk.services.embeddings_processor import BatchEmbeddingResult
from document_chunk.services.exceptions.document_chunk_exceptions import (
    DocumentPersistenceError,
)

User = get_user_model()


class TestChunkRefreshService(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpassword"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSED,
            s3_key="docs/test.pdf",
        )
        self.page = DocumentPage.objects.create(document=self.document)
        self.chunk = DocumentChunk.objects.create(
            page=self.page,
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
        self.mock_pdf_extractor = MagicMock()
        self.mock_embedding_processor = MagicMock()
        self.service = ChunkRefreshService(
            pdf_extractor=self.mock_pdf_extractor,
            embedding_processor=self.mock_embedding_processor,
        )
        self.pages = [
            {
                "page_number": 1,
                "text": "hello world foo bar",
                "words": [
                    {
                        "text": "hello",
                        "x0": 10,
                        "x1": 50,
                        "top": 10,
                        "bottom": 20,
                    },
                    {
                        "text": "world",
                        "x0": 55,
                        "x1": 100,
                        "top": 10,
                        "bottom": 20,
                    },
                    {
                        "text": "foo",
                        "x0": 10,
                        "x1": 40,
                        "top": 30,
                        "bottom": 40,
                    },
                    {
                        "text": "bar",
                        "x0": 45,
                        "x1": 80,
                        "top": 30,
                        "bottom": 40,
                    },
                ],
            }
        ]
        self.mock_pdf_extractor.extract.return_value = self.pages
        self.mock_embedding_processor.embed_batch.return_value = (
            BatchEmbeddingResult(
                embeddings=[[0.5] * 1024, [0.5] * 1024, [0.5] * 1024],
                errors={},
                throttle_count=0,
            )
        )

    # ------------------------------------------------------------------
    # refresh()
    # ------------------------------------------------------------------

    def test_refresh_updates_content_and_embedding(self):
        polygons = [
            {
                "page_number": 1,
                "points": [[0, 0], [110, 0], [110, 25], [0, 25]],
            }
        ]

        self.service.refresh(self.chunk, polygons)

        self.chunk.refresh_from_db()
        self.assertEqual(self.chunk.content, "hello world")
        self.assertEqual(list(self.chunk.embedding), [0.5] * 1024)
        self.assertEqual(self.chunk.bounding_polygons, polygons)

    def test_refresh_calls_pdf_extractor_with_correct_args(self):
        import os

        polygons = [
            {
                "page_number": 1,
                "points": [[0, 0], [110, 0], [110, 25], [0, 25]],
            }
        ]

        self.service.refresh(self.chunk, polygons)

        self.mock_pdf_extractor.extract.assert_called_once_with(
            os.environ["S3_BUCKET_NAME"],
            self.document.s3_key,
        )

    def test_refresh_calls_embedding_processor_with_extracted_text(self):
        polygons = [
            {
                "page_number": 1,
                "points": [[0, 0], [110, 0], [110, 25], [0, 25]],
            }
        ]

        self.service.refresh(self.chunk, polygons)

        self.mock_embedding_processor.embed_batch.assert_called_once()
        texts = self.mock_embedding_processor.embed_batch.call_args[0][0]
        # chunk_text, title_text, doc_text — all three derived from "hello world"
        self.assertEqual(len(texts), 3)
        self.assertIn("hello world", texts[0])

    def test_refresh_raises_value_error_when_polygons_empty(self):
        with self.assertRaises(ValueError):
            self.service.refresh(self.chunk, [])

    def test_refresh_raises_value_error_when_no_text_extracted(self):
        polygons = [
            {
                "page_number": 1,
                "points": [[900, 900], [999, 900], [999, 999], [900, 999]],
            }
        ]

        with self.assertRaises(ValueError):
            self.service.refresh(self.chunk, polygons)

    def test_refresh_returns_chunk_instance(self):
        polygons = [
            {
                "page_number": 1,
                "points": [[0, 0], [110, 0], [110, 25], [0, 25]],
            }
        ]

        result = self.service.refresh(self.chunk, polygons)

        self.assertIsInstance(result, DocumentChunk)
        self.assertEqual(result.id, self.chunk.id)

    # ------------------------------------------------------------------
    # _extract_text_from_polygons()
    # ------------------------------------------------------------------

    def test_extract_text_collects_words_inside_polygon_bbox(self):
        polygons = [
            {
                "page_number": 1,
                "points": [[0, 0], [110, 0], [110, 25], [0, 25]],
            }
        ]

        text = self.service._extract_text_from_polygons(polygons, self.pages)

        self.assertIn("hello", text)
        self.assertIn("world", text)
        self.assertNotIn("foo", text)
        self.assertNotIn("bar", text)

    def test_extract_text_spans_multiple_polygons(self):
        polygons = [
            {
                "page_number": 1,
                "points": [[0, 0], [110, 0], [110, 25], [0, 25]],
            },
            {
                "page_number": 1,
                "points": [[0, 25], [90, 25], [90, 45], [0, 45]],
            },
        ]

        text = self.service._extract_text_from_polygons(polygons, self.pages)

        self.assertIn("hello", text)
        self.assertIn("world", text)
        self.assertIn("foo", text)
        self.assertIn("bar", text)

    def test_extract_text_skips_unknown_page_numbers(self):
        polygons = [
            {
                "page_number": 99,
                "points": [[0, 0], [110, 0], [110, 25], [0, 25]],
            }
        ]

        text = self.service._extract_text_from_polygons(polygons, self.pages)

        self.assertEqual(text, "")

    def test_extract_text_returns_empty_when_no_words_in_region(self):
        polygons = [
            {
                "page_number": 1,
                "points": [[900, 900], [999, 900], [999, 999], [900, 999]],
            }
        ]

        text = self.service._extract_text_from_polygons(polygons, self.pages)

        self.assertEqual(text, "")

    def test_extract_text_sorts_words_in_reading_order(self):
        polygons = [
            {
                "page_number": 1,
                "points": [[0, 25], [90, 25], [90, 45], [0, 45]],
            }
        ]

        text = self.service._extract_text_from_polygons(polygons, self.pages)

        self.assertEqual(text, "foo bar")

    # ------------------------------------------------------------------
    # persistence error propagation
    # ------------------------------------------------------------------

    def test_refresh_propagates_persistence_error_on_save_failure(self):
        from django.db import DatabaseError

        polygons = [
            {
                "page_number": 1,
                "points": [[0, 0], [110, 0], [110, 25], [0, 25]],
            }
        ]

        with patch.object(
            self.chunk, "save", side_effect=DatabaseError("db error")
        ):
            with self.assertRaises(DocumentPersistenceError):
                self.service.refresh(self.chunk, polygons)
