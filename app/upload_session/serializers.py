from rest_framework import serializers
from upload_session.models import UploadSession
from document.models import Document
from document_type.models import DocumentType


class CreateUploadSessionSerializer(serializers.Serializer):
    document_type_id = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType.objects.all(),
        source="document_type",
    )


class UploadSessionSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(read_only=True)
    url = serializers.JSONField()
    status = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "status", "s3_key", "uploaded_at", "document_type"]
        read_only_fields = fields


class UploadSessionDetailSerializer(serializers.ModelSerializer):
    document = DocumentSerializer(read_only=True)

    class Meta:
        model = UploadSession
        fields = ["id", "status", "expires_at", "created_at", "document"]
        read_only_fields = fields
