from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer, extend_schema_field
from drf_spectacular.types import OpenApiTypes
from document.models import Document


class DocumentPresignedURLSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(read_only=True)
    url = serializers.JSONField()
    status = serializers.CharField(read_only=True)


class DocumentSerializer(serializers.ModelSerializer):
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "url", "s3_key", "uploaded_at", "file_name"]
        read_only_fields = fields

    def get_file_name(self, obj):
        # Extrae el nombre del archivo a partir de s3_key
        return obj.s3_key.split("/")[-1]
