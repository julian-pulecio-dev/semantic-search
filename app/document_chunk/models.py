import uuid
from django.db import models
from document.models import Document
from pgvector.django import VectorField


class DocumentChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    content = models.TextField()
    embedding = VectorField(dimensions=1536)
    chunk_index = models.IntegerField()
