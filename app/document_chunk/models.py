import uuid
from django.db import models
from django.core.validators import MinValueValidator
from document.models import Document
from pgvector.django import VectorField, HnswIndex


class DocumentChunk(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
        db_index=True,
    )

    content = models.TextField()

    # Contextual metadata added during chunking
    section_type = models.CharField(max_length=100, null=True, blank=True)
    section_title = models.CharField(max_length=500, null=True, blank=True)
    context_prefix = models.TextField(null=True, blank=True)

    # Multi-level embeddings
    # embedding       → full contextual chunk  ([section_type] section_title: content)
    # embedding_title → section header          ([section_type] section_title)
    # embedding_doc   → document-level context  (document name / identifier)
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
                fields=["document", "chunk_index"],
                name="unique_chunk_per_document",
            )
        ]
        indexes = [
            models.Index(fields=["document", "chunk_index"]),
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
        return f"Chunk {self.chunk_index} - Document {self.document_id}"
