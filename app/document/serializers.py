from rest_framework import serializers
from document.models import Document
from document_type.models import DocumentType


class DocumentSerializer(serializers.ModelSerializer):
    document_type = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Document
        fields = [
            "id",
            "document_type",
            "s3_key",
            "status",
            "uploaded_at",
            "user",
        ]
        read_only_fields = ["id", "s3_key", "uploaded_at", "user"]
