from rest_framework import serializers
from upload_session.models import UploadSession
from document.models import Document


class CreateUploadSessionSerializer(serializers.Serializer):
    document_type = serializers.CharField(max_length=100)


class UploadSessionSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(
        source="upload_session_id", read_only=True
    )
    document_id = serializers.UUIDField(read_only=True)
    url = serializers.JSONField()
    status = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "status", "s3_key", "uploaded_at"]
        read_only_fields = fields


class UploadSessionDetailSerializer(serializers.ModelSerializer):
    document = DocumentSerializer(read_only=True)

    class Meta:
        model = UploadSession
        fields = ["id", "status", "expires_at", "created_at", "document"]
        read_only_fields = fields
