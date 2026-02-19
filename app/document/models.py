import uuid
from django.db import models
from user.models import User


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    s3_key = models.CharField(max_length=255)
    url = models.URLField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="documents"
    )

    def __str__(self):
        return self.url
