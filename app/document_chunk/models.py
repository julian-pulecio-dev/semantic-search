import uuid
from django.db import models
from django.core.validators import MinValueValidator
from document_page.models import DocumentPage
from pgvector.django import VectorField, HnswIndex


class DocumentChunk(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    page = models.ForeignKey(
        DocumentPage,
        on_delete=models.CASCADE,
        related_name="chunks",
        db_index=True,
    )

    content = models.TextField()

    section_type = models.CharField(max_length=100, null=True, blank=True)
    section_title = models.CharField(max_length=500, null=True, blank=True)
    context_prefix = models.TextField(null=True, blank=True)

    embedding = VectorField(
        dimensions=1024,
        null=True,
        blank=True,
    )
    embedding_title = VectorField(
        dimensions=1024,
        null=True,
        blank=True,
    )
    embedding_doc = VectorField(
        dimensions=1024,
        null=True,
        blank=True,
    )
    chunk_index = models.PositiveIntegerField(
        validators=[MinValueValidator(0)]
    )

    bounding_polygons = models.JSONField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["page", "chunk_index"],
                name="unique_chunk_per_page",
            )
        ]
        indexes = [
            models.Index(fields=["page", "chunk_index"]),
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            HnswIndex(
                name="chunk_embedding_title_hnsw",
                fields=["embedding_title"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            HnswIndex(
                name="chunk_embedding_doc_hnsw",
                fields=["embedding_doc"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} - Page {self.page_id}"
