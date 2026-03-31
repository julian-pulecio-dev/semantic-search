import unittest
from unittest.mock import MagicMock, patch

from django.db import DatabaseError
from django.test import TestCase
from django.contrib.auth import get_user_model

from document.models import Document
from document_chunk.models import DocumentChunk
from document_chunk.services.document_chunk_processor import (
    Chunk,
    DocumentChunkProcessor,
    DocumentPersistenceError,
)
from document_chunk.services.embeddings_processor import BatchEmbeddingResult
from document_chunk.services.exceptions.embedding_exceptions import (
    EmbeddingError,
)

User = get_user_model()


class TestChunk(unittest.TestCase):
    def test_with_embedding_returns_new_chunk_with_embedding_attached(self):
        chunk = Chunk(content="text", page_number=1, document_id=1)
        result = chunk.with_embedding([0.1, 0.2])
        self.assertEqual(result.content, "text")
        self.assertEqual(result.page_number, 1)
        self.assertEqual(result.document_id, 1)
        self.assertEqual(result.embedding, [0.1, 0.2])

    def test_with_embedding_does_not_mutate_the_original_chunk(self):
        chunk = Chunk(content="text", page_number=1, document_id=1)
        chunk.with_embedding([0.1])
        self.assertIsNone(chunk.embedding)

    def test_chunk_is_immutable(self):
        chunk = Chunk(content="text", page_number=1, document_id=1)
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
            embedding_processor=MagicMock(),
            splitter=MagicMock(),
        )

    def test_post_init_sets_document_status_to_processing(self):
        self._make_processor()
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSING)

    def test_post_init_creates_default_dependencies_when_not_provided(self):
        with patch(
            "document_chunk.services.document_chunk_processor.EmbeddingsProcessor"
        ), patch(
            "document_chunk.services.document_chunk_processor.PDFTextExtractor"
        ), patch(
            "document_chunk.services.document_chunk_processor"
            ".RecursiveCharacterTextSplitter"
        ):
            processor = DocumentChunkProcessor(document=self.document)
        self.assertIsNotNone(processor.pdf_extractor)
        self.assertIsNotNone(processor.embedding_processor)
        self.assertIsNotNone(processor.splitter)


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
        self.mock_embedding_processor = MagicMock()
        self.mock_splitter = MagicMock()

    def _make_processor(self):
        return DocumentChunkProcessor(
            document=self.document,
            pdf_extractor=self.mock_pdf_extractor,
            embedding_processor=self.mock_embedding_processor,
            splitter=self.mock_splitter,
        )

    # --- _text_to_chunks ---

    def test_text_to_chunks_splits_page_text_and_returns_chunks(self):
        processor = self._make_processor()
        self.mock_splitter.split_text.return_value = ["chunk 1", "chunk 2"]

        chunks = processor._text_to_chunks(
            [{"page_number": 3, "text": "some text"}]
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].content, "chunk 1")
        self.assertEqual(chunks[0].page_number, 3)
        self.assertEqual(chunks[1].content, "chunk 2")

    def test_text_to_chunks_assigns_correct_document_id(self):
        processor = self._make_processor()
        self.mock_splitter.split_text.return_value = ["text"]

        chunks = processor._text_to_chunks(
            [{"page_number": 1, "text": "text"}]
        )

        self.assertEqual(chunks[0].document_id, self.document.id)

    def test_text_to_chunks_handles_multiple_pages(self):
        processor = self._make_processor()
        self.mock_splitter.split_text.side_effect = [
            ["p1-c1"],
            ["p2-c1", "p2-c2"],
        ]

        pages = [
            {"page_number": 1, "text": "page one"},
            {"page_number": 2, "text": "page two"},
        ]
        chunks = processor._text_to_chunks(pages)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].page_number, 1)
        self.assertEqual(chunks[1].page_number, 2)

    # --- _attach_embeddings ---

    def test_attach_embeddings_returns_chunks_with_embeddings(self):
        processor = self._make_processor()
        chunks = [
            Chunk(content="a", page_number=1, document_id=self.document.id),
            Chunk(content="b", page_number=2, document_id=self.document.id),
        ]
        self.mock_embedding_processor.embed_batch.return_value = (
            BatchEmbeddingResult(
                embeddings=[[0.1, 0.2], [0.3, 0.4]],
                errors={},
                throttle_count=0,
            )
        )

        result = processor._attach_embeddings(chunks)

        self.assertEqual(result[0].embedding, [0.1, 0.2])
        self.assertEqual(result[1].embedding, [0.3, 0.4])

    def test_attach_embeddings_returns_unchanged_chunks_when_embed_batch_raises(
        self,
    ):
        processor = self._make_processor()
        chunks = [
            Chunk(content="a", page_number=1, document_id=self.document.id)
        ]
        self.mock_embedding_processor.embed_batch.side_effect = EmbeddingError(
            "fail"
        )

        result = processor._attach_embeddings(chunks)

        self.assertIsNone(result[0].embedding)

    def test_attach_embeddings_returns_unchanged_chunks_when_raise_on_errors_raises(
        self,
    ):
        processor = self._make_processor()
        chunks = [
            Chunk(content="a", page_number=1, document_id=self.document.id)
        ]
        self.mock_embedding_processor.embed_batch.return_value = (
            BatchEmbeddingResult(
                embeddings=[None],
                errors={0: EmbeddingError("fail")},
                throttle_count=0,
            )
        )

        result = processor._attach_embeddings(chunks)

        self.assertIsNone(result[0].embedding)

    # --- _attach_embeddings_in_batches ---

    def test_attach_embeddings_in_batches_processes_all_chunks_across_batches(
        self,
    ):
        processor = self._make_processor()
        processor.embedding_batch_size = 2
        chunks = [
            Chunk(content=str(i), page_number=1, document_id=self.document.id)
            for i in range(5)
        ]
        self.mock_embedding_processor.embed_batch.return_value = (
            BatchEmbeddingResult(
                embeddings=[[float(i)] for i in range(2)],
                errors={},
                throttle_count=0,
            )
        )

        result = processor._attach_embeddings_in_batches(chunks)

        self.assertEqual(len(result), 5)
        # ceil(5/2) = 3 batches
        self.assertEqual(
            self.mock_embedding_processor.embed_batch.call_count, 3
        )

    # --- _save_chunks ---

    def test_save_chunks_persists_all_chunks_to_db(self):
        processor = self._make_processor()
        chunks = [
            Chunk(
                content="chunk text",
                page_number=1,
                document_id=self.document.id,
                embedding=[0.1] * 1024,
            )
        ]

        processor._save_chunks(chunks)

        saved = DocumentChunk.objects.filter(document=self.document)
        self.assertEqual(saved.count(), 1)
        self.assertEqual(saved.first().content, "chunk text")
        self.assertEqual(saved.first().chunk_index, 0)

    def test_save_chunks_assigns_sequential_chunk_indices(self):
        processor = self._make_processor()
        chunks = [
            Chunk(
                content="first", page_number=1, document_id=self.document.id
            ),
            Chunk(
                content="second", page_number=1, document_id=self.document.id
            ),
        ]

        processor._save_chunks(chunks)

        indices = list(
            DocumentChunk.objects.filter(document=self.document)
            .order_by("chunk_index")
            .values_list("chunk_index", flat=True)
        )
        self.assertEqual(indices, [0, 1])

    def test_save_chunks_raises_persistence_error_on_database_failure(self):
        processor = self._make_processor()
        chunks = [
            Chunk(content="a", page_number=1, document_id=self.document.id)
        ]

        with patch(
            "document_chunk.services.document_chunk_processor"
            ".DocumentChunk.objects.bulk_create",
            side_effect=DatabaseError("db error"),
        ):
            with self.assertRaises(DocumentPersistenceError):
                processor._save_chunks(chunks)
