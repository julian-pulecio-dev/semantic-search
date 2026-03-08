import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class DocumentType(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=50,
        unique=True,
    )

    authority_score = models.FloatField(
        default=0.5,
        validators=[
            MinValueValidator(0.0),
            MaxValueValidator(1.0),
        ],
        db_index=True,
    )

    description = models.TextField(
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-authority_score", "name"]

        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["authority_score"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.authority_score})"
