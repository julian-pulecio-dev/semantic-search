import uuid
from django.db import models
from django.core.validators import MinValueValidator
from document.models import Document


class DocumentPage(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="pages",
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    number_of_chunks = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        null=True,
        blank=True,
    )

    number_of_chunks_processed = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "created_at"],
                name="unique_page_per_document",
            )
        ]

    def __str__(self):
        return f"Page {self.id} - Document {self.document_id}"
