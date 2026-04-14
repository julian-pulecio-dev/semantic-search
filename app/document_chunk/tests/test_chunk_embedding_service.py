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


class TestChunkEmbeddingServiceProcessBatch(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="embed@test.com", password="testpassword"
        )
        self.document = Document.objects.create(
            user=self.user,
            status=Document.Status.PROCESSING,
            s3_key="docs/embed.pdf",
            embedding_batches_total=1,
            embedding_batches_done=0,
        )
        self.chunk1 = DocumentChunk.objects.create(
            document=self.document,
            content="first chunk",
            chunk_index=0,
        )
        self.chunk2 = DocumentChunk.objects.create(
            document=self.document,
            content="second chunk",
            chunk_index=1,
        )
        self.mock_processor = MagicMock()
        self.service = ChunkEmbeddingService(
            embedding_processor=self.mock_processor
        )

    def _chunk_ids(self):
        return [str(self.chunk1.id), str(self.chunk2.id)]

    # --- embedding attachment ---

    def test_attaches_embeddings_to_chunks(self):
        self.mock_processor.embed_batch.return_value = BatchEmbeddingResult(
            embeddings=[[0.1] * 1024, [0.2] * 1024],
            errors={},
            throttle_count=0,
        )

        self.service.process_batch(str(self.document.id), self._chunk_ids())

        import numpy as np

        self.chunk1.refresh_from_db()
        self.chunk2.refresh_from_db()
        self.assertTrue(np.allclose(self.chunk1.embedding, [0.1] * 1024))
        self.assertTrue(np.allclose(self.chunk2.embedding, [0.2] * 1024))

    def test_leaves_embeddings_null_when_bedrock_raises(self):
        self.mock_processor.embed_batch.side_effect = EmbeddingError("timeout")

        self.service.process_batch(str(self.document.id), self._chunk_ids())

        self.chunk1.refresh_from_db()
        self.chunk2.refresh_from_db()
        self.assertIsNone(self.chunk1.embedding)
        self.assertIsNone(self.chunk2.embedding)

    def test_leaves_embeddings_null_when_raise_on_errors_raises(self):
        self.mock_processor.embed_batch.return_value = BatchEmbeddingResult(
            embeddings=[None, None],
            errors={0: EmbeddingError("err"), 1: EmbeddingError("err")},
            throttle_count=0,
        )

        self.service.process_batch(str(self.document.id), self._chunk_ids())

        self.chunk1.refresh_from_db()
        self.assertIsNone(self.chunk1.embedding)

    # --- document finalisation ---

    def test_increments_embedding_batches_done(self):
        self.mock_processor.embed_batch.return_value = BatchEmbeddingResult(
            embeddings=[[0.1] * 1024, [0.2] * 1024],
            errors={},
            throttle_count=0,
        )

        self.service.process_batch(str(self.document.id), self._chunk_ids())

        self.document.refresh_from_db()
        self.assertEqual(self.document.embedding_batches_done, 1)

    def test_marks_document_processed_when_all_batches_done_and_no_nulls(self):
        self.mock_processor.embed_batch.return_value = BatchEmbeddingResult(
            embeddings=[[0.1] * 1024, [0.2] * 1024],
            errors={},
            throttle_count=0,
        )

        self.service.process_batch(str(self.document.id), self._chunk_ids())

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSED)

    def test_marks_document_incompleted_when_all_batches_done_but_some_null(
        self,
    ):
        self.mock_processor.embed_batch.side_effect = EmbeddingError("fail")

        self.service.process_batch(str(self.document.id), self._chunk_ids())

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.INCOMPLETED)

    def test_does_not_finalise_document_when_batches_not_complete(self):
        self.document.embedding_batches_total = 3
        self.document.save(update_fields=["embedding_batches_total"])

        self.mock_processor.embed_batch.return_value = BatchEmbeddingResult(
            embeddings=[[0.1] * 1024, [0.2] * 1024],
            errors={},
            throttle_count=0,
        )

        self.service.process_batch(str(self.document.id), self._chunk_ids())

        self.document.refresh_from_db()
        # Still PROCESSING — only 1 of 3 batches done
        self.assertEqual(self.document.status, Document.Status.PROCESSING)
        self.assertEqual(self.document.embedding_batches_done, 1)

    def test_does_not_finalise_when_batches_total_is_none(self):
        self.document.embedding_batches_total = None
        self.document.save(update_fields=["embedding_batches_total"])

        self.mock_processor.embed_batch.return_value = BatchEmbeddingResult(
            embeddings=[[0.1] * 1024, [0.2] * 1024],
            errors={},
            throttle_count=0,
        )

        self.service.process_batch(str(self.document.id), self._chunk_ids())

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSING)

    def test_skips_gracefully_when_no_chunks_found(self):
        import uuid

        self.service.process_batch(str(self.document.id), [str(uuid.uuid4())])

        # No exception, document still finalised (batch counted as done)
        self.document.refresh_from_db()
        self.assertEqual(self.document.embedding_batches_done, 1)

    def test_does_not_raise_when_document_not_found(self):
        import uuid

        # Should log and return without raising
        self.service.process_batch(str(uuid.uuid4()), self._chunk_ids())
