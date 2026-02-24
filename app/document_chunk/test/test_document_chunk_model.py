import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from user.models import User
from document.models import Document
from document_chunk.models import DocumentChunk


class DocumentChunkModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="password123"
        )

        self.document = Document.objects.create(
            s3_key="documents/test.pdf",
            url="https://s3.amazonaws.com/test.pdf",
            user=self.user,
        )

        self.embedding = [0.1] * 1536

    def test_create_document_chunk(self):
        chunk = DocumentChunk.objects.create(
            document=self.document,
            content="Test content",
            embedding=self.embedding,
            chunk_index=0,
        )

        self.assertIsInstance(chunk.id, uuid.UUID)
        self.assertEqual(chunk.document, self.document)

    def test_unique_constraint(self):
        DocumentChunk.objects.create(
            document=self.document,
            content="Chunk",
            embedding=self.embedding,
            chunk_index=0,
        )

        with self.assertRaises(IntegrityError):
            DocumentChunk.objects.create(
                document=self.document,
                content="Duplicate",
                embedding=self.embedding,
                chunk_index=0,
            )

    def test_min_value_validator(self):
        chunk = DocumentChunk(
            document=self.document,
            content="Invalid",
            embedding=self.embedding,
            chunk_index=-1,
        )

        with self.assertRaises(ValidationError):
            chunk.full_clean()

    def test_cascade_delete_document(self):
        chunk = DocumentChunk.objects.create(
            document=self.document,
            content="Test",
            embedding=self.embedding,
            chunk_index=0,
        )

        self.document.delete()

        self.assertFalse(DocumentChunk.objects.filter(id=chunk.id).exists())
