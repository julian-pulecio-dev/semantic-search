import unittest
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.contrib.auth import get_user_model

from document.models import Document
from document_chunk.services.document_chunk_processor import (
    Chunk,
    DocumentChunkProcessor,
    DocumentPersistenceError,
)
from document_chunk.services.chunk_bounding_polygon import PagePolygon

User = get_user_model()


class TestChunk(unittest.TestCase):
    def test_chunk_is_immutable(self):
        chunk = Chunk(content="text", chunk_index=0, document_id=1)
        with self.assertRaises((AttributeError, TypeError)):
            chunk.content = "other"


class TestDocumentChunkProcessorInit(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpassword"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PENDING,
            s3_key="docs/test.pdf",
        )

    def _make_processor(self):
        return DocumentChunkProcessor(
            document=self.document,
            pdf_extractor=MagicMock(),
            splitter=MagicMock(),
            bounding_polygon_resolver=MagicMock(),
        )

    def test_post_init_sets_document_status_to_processing(self):
        self._make_processor()
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSING)

    def test_post_init_creates_default_dependencies_when_not_provided(self):
        with patch(
            "document_chunk.services.document_chunk_processor.PDFTextExtractor"
        ), patch(
            "document_chunk.services.document_chunk_processor"
            ".RecursiveCharacterTextSplitter"
        ), patch(
            "document_chunk.services.document_chunk_processor.ChunkBoundingPolygon"
        ):
            processor = DocumentChunkProcessor(document=self.document)
        self.assertIsNotNone(processor.pdf_extractor)
        self.assertIsNotNone(processor.splitter)
        self.assertIsNotNone(processor.bounding_polygon_resolver)


class TestDocumentChunkProcessorMethods(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpassword"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PENDING,
            s3_key="docs/test.pdf",
        )
        self.mock_pdf_extractor = MagicMock()
        self.mock_splitter = MagicMock()
        self.mock_bounding_polygon_resolver = MagicMock()
        self.mock_bounding_polygon_resolver.resolve.return_value = ([], {})

    def _make_processor(self, chunk_batch_size=10):
        return DocumentChunkProcessor(
            document=self.document,
            pdf_extractor=self.mock_pdf_extractor,
            splitter=self.mock_splitter,
            bounding_polygon_resolver=self.mock_bounding_polygon_resolver,
            chunk_batch_size=chunk_batch_size,
        )

    # --- _text_to_chunks ---

    def test_text_to_chunks_calls_split_text_once_on_full_document_text(self):
        processor = self._make_processor()
        self.mock_splitter.split_text.return_value = ["chunk 1"]

        processor._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )

        self.mock_splitter.split_text.assert_called_once_with("some text")

    def test_text_to_chunks_concatenates_pages_with_double_newline(self):
        processor = self._make_processor()
        self.mock_splitter.split_text.return_value = ["text"]

        processor._text_to_chunks(
            [
                {"page_number": 1, "text": "page one", "words": []},
                {"page_number": 2, "text": "page two", "words": []},
            ]
        )

        self.mock_splitter.split_text.assert_called_once_with(
            "page one\n\npage two"
        )

    def test_text_to_chunks_returns_chunk_for_each_split(self):
        processor = self._make_processor()
        self.mock_splitter.split_text.return_value = ["chunk 1", "chunk 2"]

        chunks = processor._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].content, "chunk 1")
        self.assertEqual(chunks[1].content, "chunk 2")

    def test_text_to_chunks_bounding_polygons_stored_in_chunk(self):
        processor = self._make_processor()
        self.mock_splitter.split_text.return_value = ["chunk 1"]
        polygon = PagePolygon(
            page_number=2, points=[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]
        )
        self.mock_bounding_polygon_resolver.resolve.return_value = (
            [polygon],
            {},
        )

        chunks = processor._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )

        self.assertEqual(
            chunks[0].bounding_polygons,
            [
                {
                    "page_number": 2,
                    "points": [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0]],
                }
            ],
        )

    def test_text_to_chunks_bounding_polygons_empty_list_when_no_polygons(
        self,
    ):
        processor = self._make_processor()
        self.mock_splitter.split_text.return_value = ["chunk 1"]

        chunks = processor._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )

        self.assertEqual(chunks[0].bounding_polygons, [])

    def test_text_to_chunks_page_cursors_passed_across_chunks(self):
        processor = self._make_processor()
        self.mock_splitter.split_text.return_value = ["chunk 1", "chunk 2"]
        first_cursors = {1: 5}
        self.mock_bounding_polygon_resolver.resolve.side_effect = [
            ([], first_cursors),
            ([], {1: 10}),
        ]

        processor._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )

        calls = self.mock_bounding_polygon_resolver.resolve.call_args_list
        self.assertEqual(calls[1][0][2], first_cursors)

    def test_text_to_chunks_assigns_correct_document_id(self):
        processor = self._make_processor()
        self.mock_splitter.split_text.return_value = ["text"]

        chunks = processor._text_to_chunks(
            [{"page_number": 1, "text": "text", "words": []}]
        )

        self.assertEqual(chunks[0].document_id, self.document.id)

    # --- process() ---

    def test_process_returns_batches_of_chunks(self):
        processor = self._make_processor(chunk_batch_size=2)
        self.mock_pdf_extractor.extract.return_value = [
            {"page_number": 1, "text": "a b c d e", "words": []}
        ]
        self.mock_splitter.split_text.return_value = ["c1", "c2", "c3"]

        import os

        with patch.dict(os.environ, {"S3_BUCKET_NAME": "test-bucket"}):
            batches = processor.process()

        # 3 chunks, batch_size=2 → 2 batches: [2 chunks, 1 chunk]
        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]), 2)
        self.assertEqual(len(batches[1]), 1)

    def test_process_marks_document_processed_when_no_chunks(self):
        processor = self._make_processor()
        self.mock_pdf_extractor.extract.return_value = [
            {"page_number": 1, "text": "", "words": []}
        ]
        self.mock_splitter.split_text.return_value = []

        import os

        with patch.dict(os.environ, {"S3_BUCKET_NAME": "test-bucket"}):
            batches = processor.process()

        self.assertEqual(batches, [])
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSED)
