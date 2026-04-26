from rest_framework import serializers
from document.models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "s3_key",
            "status",
            "uploaded_at",
            "user",
        ]
        read_only_fields = ["id", "s3_key", "status", "uploaded_at", "user"]
