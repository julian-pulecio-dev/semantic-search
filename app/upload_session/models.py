import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta
from user.models import User


class UploadSession(models.Model):

    class Status(models.TextChoices):
        CREATED = "CREATED", "CREATED"
        COMPLETED = "COMPLETED", "COMPLETED"
        FAILED = "FAILED", "FAILED"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    document = models.ForeignKey(
        "document.Document",
        on_delete=models.CASCADE,
        related_name="upload_sessions",
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )

    expires_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def default_expiration():
        return timezone.now() + timedelta(minutes=15)
