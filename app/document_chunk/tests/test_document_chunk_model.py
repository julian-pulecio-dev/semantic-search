import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from user.models import User
from document.models import Document
from document_page.models import DocumentPage
from document_chunk.models import DocumentChunk


class DocumentChunkModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="password123"
        )
        self.document = Document.objects.create(
            s3_key="documents/test.pdf",
            status=Document.Status.PROCESSED,
            user=self.user,
        )
        self.page = DocumentPage.objects.create(document=self.document)
        self.embedding = [0.1] * 1024

    def _create_chunk(self, chunk_index=0, **kwargs):
        defaults = dict(
            document=self.document,
            start_page=self.page,
            end_page=self.page,
            content="Test content",
            embedding=self.embedding,
            chunk_index=chunk_index,
        )
        defaults.update(kwargs)
        return DocumentChunk.objects.create(**defaults)

    def test_create_document_chunk(self):
        chunk = self._create_chunk()

        self.assertIsInstance(chunk.id, uuid.UUID)
        self.assertEqual(chunk.start_page, self.page)
        self.assertEqual(chunk.document, self.document)

    def test_unique_constraint_per_document(self):
        self._create_chunk(chunk_index=0)

        with self.assertRaises(IntegrityError):
            self._create_chunk(chunk_index=0)

    def test_min_value_validator(self):
        chunk = DocumentChunk(
            document=self.document,
            start_page=self.page,
            end_page=self.page,
            content="Invalid",
            embedding=self.embedding,
            chunk_index=-1,
        )

        with self.assertRaises(ValidationError):
            chunk.full_clean()

    def test_create_chunk_without_embedding(self):
        chunk = self._create_chunk(embedding=None)

        chunk.refresh_from_db()
        self.assertIsNone(chunk.embedding)

    def test_cascade_delete_from_page(self):
        chunk = self._create_chunk()

        self.page.delete()

        self.assertFalse(DocumentChunk.objects.filter(id=chunk.id).exists())

    def test_cascade_delete_from_document(self):
        chunk = self._create_chunk()

        self.document.delete()

        self.assertFalse(DocumentChunk.objects.filter(id=chunk.id).exists())
