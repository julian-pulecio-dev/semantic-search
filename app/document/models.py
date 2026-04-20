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
    s3_key = models.CharField(
        max_length=255, unique=True, null=True, blank=True, editable=False
    )
    status = models.CharField(
        choices=Status.choices,
        max_length=20,
        null=False,
        blank=False,
    )
    number_of_pages = models.PositiveIntegerField(
        null=True, blank=True, default=None
    )
    number_of_pages_processed = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="documents"
    )

    def __str__(self):
        return str(self.id)
