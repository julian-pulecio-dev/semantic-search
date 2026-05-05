from unittest.mock import MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from document.models import Document
from document_chunk.models import DocumentChunk
from document_chunk.services.chunk_embedding_service import (
    ChunkEmbeddingService,
)
from document_chunk.services.embeddings_processor import BatchEmbeddingResult
from document_chunk.services.exceptions.embedding_exceptions import (
    EmbeddingError,
)

User = get_user_model()

_EMBEDDING = [0.1] * 1024
_BATCH_RESULT = BatchEmbeddingResult(
    embeddings=[_EMBEDDING, _EMBEDDING, _EMBEDDING],
    errors={},
    throttle_count=0,
)
_POLYGONS = [{"page_number": 1, "points": [[0, 0], [1, 0], [1, 1], [0, 1]]}]
_ABSENT = (
    object()
)  # sentinel: key present but caller wants the default polygons


def _chunk_data(
    chunk_index=0, content="chunk text", bounding_polygons=_ABSENT
):
    return {
        "content": content,
        "chunk_index": chunk_index,
        "section_type": "Legal",
        "section_title": "chunk text",
        "context_prefix": "[Legal] chunk text",
        "bounding_polygons": (
            _POLYGONS if bounding_polygons is _ABSENT else bounding_polygons
        ),
    }


class TestChunkEmbeddingServiceProcessBatch(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="embed@test.com", password="testpassword"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSING,
            s3_key="docs/embed.pdf",
            number_of_pages=1,
        )
        self.mock_processor = MagicMock()
        self.mock_processor.embed_batch.return_value = _BATCH_RESULT
        self.service = ChunkEmbeddingService(
            embedding_processor=self.mock_processor,
        )

    # --- persistence ---

    def test_persists_chunk_to_database(self):
        self.service.process_batch(
            str(self.document.id), [_chunk_data(chunk_index=0)]
        )

        chunk = DocumentChunk.objects.get(
            start_page__document=self.document, chunk_index=0
        )
        self.assertEqual(chunk.content, "chunk text")
        self.assertEqual(chunk.section_type, "Legal")

    def test_persists_bounding_polygons_from_message(self):
        self.service.process_batch(
            str(self.document.id), [_chunk_data(chunk_index=0)]
        )

        chunk = DocumentChunk.objects.get(
            start_page__document=self.document, chunk_index=0
        )
        self.assertEqual(chunk.bounding_polygons, _POLYGONS)

    def test_persists_null_bounding_polygons_when_absent(self):
        self.service.process_batch(
            str(self.document.id),
            [_chunk_data(chunk_index=0, bounding_polygons=None)],
        )

        chunk = DocumentChunk.objects.get(
            start_page__document=self.document, chunk_index=0
        )
        self.assertIsNone(chunk.bounding_polygons)

    def test_persists_multiple_chunks(self):
        self.service.process_batch(
            str(self.document.id),
            [
                _chunk_data(chunk_index=0),
                _chunk_data(chunk_index=1, content="second"),
            ],
        )

        self.assertEqual(
            DocumentChunk.objects.filter(
                start_page__document=self.document
            ).count(),
            2,
        )

    # --- embeddings ---

    def test_attaches_embeddings_to_persisted_chunk(self):
        import numpy as np

        self.service.process_batch(
            str(self.document.id), [_chunk_data(chunk_index=0)]
        )

        chunk = DocumentChunk.objects.get(
            start_page__document=self.document, chunk_index=0
        )
        self.assertTrue(np.allclose(chunk.embedding, _EMBEDDING))
        self.assertTrue(np.allclose(chunk.embedding_title, _EMBEDDING))
        self.assertTrue(np.allclose(chunk.embedding_doc, _EMBEDDING))

    def test_leaves_embeddings_null_when_embed_batch_raises(self):
        self.mock_processor.embed_batch.side_effect = EmbeddingError("timeout")

        self.service.process_batch(
            str(self.document.id), [_chunk_data(chunk_index=0)]
        )

        chunk = DocumentChunk.objects.get(
            start_page__document=self.document, chunk_index=0
        )
        self.assertIsNone(chunk.embedding)
        self.assertIsNone(chunk.embedding_title)
        self.assertIsNone(chunk.embedding_doc)

    def test_continues_to_next_chunk_when_embedding_fails(self):
        self.mock_processor.embed_batch.side_effect = [
            EmbeddingError("fail"),
            _BATCH_RESULT,
        ]

        self.service.process_batch(
            str(self.document.id),
            [
                _chunk_data(chunk_index=0),
                _chunk_data(chunk_index=1, content="second"),
            ],
        )

        chunk0 = DocumentChunk.objects.get(
            start_page__document=self.document, chunk_index=0
        )
        chunk1 = DocumentChunk.objects.get(
            start_page__document=self.document, chunk_index=1
        )
        self.assertIsNone(chunk0.embedding)
        self.assertIsNotNone(chunk1.embedding)

    # --- document finalisation ---

    def test_increments_number_of_pages_processed(self):
        self.service.process_batch(str(self.document.id), [_chunk_data()])

        self.document.refresh_from_db()
        self.assertEqual(self.document.number_of_pages_processed, 1)

    def test_marks_document_processed_when_all_pages_done_and_no_nulls(self):
        self.service.process_batch(str(self.document.id), [_chunk_data()])

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSED)

    def test_marks_document_incompleted_when_all_pages_done_but_some_null(
        self,
    ):
        self.mock_processor.embed_batch.side_effect = EmbeddingError("fail")

        self.service.process_batch(str(self.document.id), [_chunk_data()])

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.INCOMPLETED)

    def test_does_not_finalise_document_when_pages_not_complete(self):
        self.document.number_of_pages = 3
        self.document.save(update_fields=["number_of_pages"])

        self.service.process_batch(str(self.document.id), [_chunk_data()])

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSING)
        self.assertEqual(self.document.number_of_pages_processed, 1)

    def test_does_not_finalise_when_number_of_pages_is_none(self):
        self.document.number_of_pages = None
        self.document.save(update_fields=["number_of_pages"])

        self.service.process_batch(str(self.document.id), [_chunk_data()])

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSING)

    def test_skips_gracefully_when_document_not_found(self):
        import uuid

        self.service.process_batch(str(uuid.uuid4()), [_chunk_data()])

        self.assertEqual(DocumentChunk.objects.count(), 0)
