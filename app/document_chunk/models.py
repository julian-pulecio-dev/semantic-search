import uuid
from django.db import models
from document_page.models import DocumentPage
from pgvector.django import VectorField, HnswIndex
from pgvector.django import VectorField, HnswIndex
from document.models import Document

class DocumentChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    start_page = models.ForeignKey(
        DocumentPage,
        on_delete=models.CASCADE,
        related_name="chunks_start",
    )

    end_page = models.ForeignKey(
        DocumentPage,
        on_delete=models.CASCADE,
        related_name="chunks_end",
    )

    chunk_index = models.PositiveIntegerField()

    content = models.TextField()

    # contexto semántico
    section_title = models.CharField(max_length=500, null=True, blank=True)
    context_prefix = models.TextField(null=True, blank=True)

    # embeddings
    embedding = VectorField(dimensions=1024, null=True, blank=True)
    embedding_title = VectorField(dimensions=1024, null=True, blank=True)
    embedding_doc = VectorField(dimensions=1024, null=True, blank=True)

    # geometría opcional
    bounding_polygons = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["chunk_index"]

        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="unique_chunk_per_document",
            )
        ]

        indexes = [
            models.Index(fields=["document", "chunk_index"]),
            models.Index(fields=["start_page", "end_page"]),

            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
