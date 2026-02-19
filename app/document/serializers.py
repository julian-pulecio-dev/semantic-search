from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer, extend_schema_field
from drf_spectacular.types import OpenApiTypes
from document.models import Document


@extend_schema_serializer(
    examples=[
        {
            "file": "binary file data",
            "url": "https://bucket.s3.amazonaws.com/documents/test.txt",
            "uploaded_at": "2024-01-01T12:00:00Z",
        }
    ]
)
class CreateDocumentSerializer(serializers.Serializer):
    """Serializer for Document model"""

    file = serializers.FileField(write_only=True)

    # Esta línea es la clave
    file = extend_schema_field(OpenApiTypes.BINARY)(file)

    class Meta:
        model = Document
        fields = ("file", "url", "uploaded_at")
        read_only_fields = ("url", "uploaded_at")


class DocumentSerializer(serializers.ModelSerializer):
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "url", "s3_key", "uploaded_at", "file_name"]
        read_only_fields = fields

    def get_file_name(self, obj):
        # Extrae el nombre del archivo a partir de s3_key
        return obj.s3_key.split("/")[-1]
