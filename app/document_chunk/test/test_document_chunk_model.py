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

    def test_create_document_chunk(self):
        chunk = DocumentChunk.objects.create(
            page=self.page,
            content="Test content",
            embedding=self.embedding,
            chunk_index=0,
        )

        self.assertIsInstance(chunk.id, uuid.UUID)
        self.assertEqual(chunk.page, self.page)

    def test_unique_constraint_per_page(self):
        DocumentChunk.objects.create(
            page=self.page,
            content="Chunk",
            embedding=self.embedding,
            chunk_index=0,
        )

        with self.assertRaises(IntegrityError):
            DocumentChunk.objects.create(
                page=self.page,
                content="Duplicate",
                embedding=self.embedding,
                chunk_index=0,
            )

    def test_min_value_validator(self):
        chunk = DocumentChunk(
            page=self.page,
            content="Invalid",
            embedding=self.embedding,
            chunk_index=-1,
        )

        with self.assertRaises(ValidationError):
            chunk.full_clean()

    def test_create_chunk_without_embedding(self):
        chunk = DocumentChunk.objects.create(
            page=self.page,
            content="Chunk without embedding",
            embedding=None,
            chunk_index=0,
        )

        chunk.refresh_from_db()
        self.assertIsNone(chunk.embedding)

    def test_cascade_delete_from_page(self):
        chunk = DocumentChunk.objects.create(
            page=self.page,
            content="Test",
            embedding=self.embedding,
            chunk_index=0,
        )

        self.page.delete()

        self.assertFalse(DocumentChunk.objects.filter(id=chunk.id).exists())

    def test_cascade_delete_from_document(self):
        chunk = DocumentChunk.objects.create(
            page=self.page,
            content="Test",
            embedding=self.embedding,
            chunk_index=0,
        )

        self.document.delete()

        self.assertFalse(DocumentChunk.objects.filter(id=chunk.id).exists())
