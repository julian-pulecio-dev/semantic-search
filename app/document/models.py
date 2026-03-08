import uuid
from django.db import models
from user.models import User
from document_type.models import DocumentType


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "PENDING"
        PROCESSING = "PROCESSING", "PROCESSING"
        READY = "READY", "READY"
        FAILED = "FAILED", "FAILED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        null=True,
        related_name="documents",
    )
    s3_key = models.CharField(
        max_length=255, unique=True, null=True, blank=True, editable=False
    )
    status = models.CharField(
        choices=Status.choices,
        max_length=20,
        null=False,
        blank=False,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="documents"
    )

    def __str__(self):
        return str(self.id)
