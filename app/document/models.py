import uuid
from django.db import models
from user.models import User


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "PENDING"
        PROCESSING = "PROCESSING", "PROCESSING"
        PROCESSED = "PROCESSED", "PROCESSED"
        FAILED = "FAILED", "FAILED"
        INCOMPLETED = "INCOMPLETED", "INCOMPLETED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.OneToOneField(
        "document.Document",
        on_delete=models.CASCADE,
        related_name="upload_session",
        null=True,
        blank=True,
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
    embedding_batches_total = models.PositiveIntegerField(
        null=True, blank=True, default=None
    )
    embedding_batches_done = models.PositiveIntegerField(default=0)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="documents"
    )

    def __str__(self):
        return str(self.id)
