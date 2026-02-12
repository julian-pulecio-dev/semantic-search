from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer, extend_schema_field
from drf_spectacular.types import OpenApiTypes
from core.models import Document


@extend_schema_serializer(
    examples=[
        {
            "file": "binary file data",
            "url": "https://bucket.s3.amazonaws.com/documents/test.txt",
            "uploaded_at": "2024-01-01T12:00:00Z",
        }
    ]
)
class DocumentSerializer(serializers.Serializer):
    """Serializer for Document model"""

    file = serializers.FileField(write_only=True)

    # Esta línea es la clave
    file = extend_schema_field(OpenApiTypes.BINARY)(file)

    class Meta:
        model = Document
        fields = ("file", "url", "uploaded_at")
        read_only_fields = ("url", "uploaded_at")
