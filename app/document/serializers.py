from rest_framework import serializers
from document.models import Document


class DocumentPresignedURLSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(read_only=True)
    url = serializers.JSONField()
    status = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "s3_key", "status", "uploaded_at", "user"]
        read_only_fields = ["id", "s3_key", "uploaded_at", "user"]
