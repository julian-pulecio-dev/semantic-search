from rest_framework import serializers
from document_page.models import DocumentPage


class DocumentPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentPage
        fields = [
            "id",
            "document",
            "created_at",
        ]
        read_only_fields = ["id", "document", "created_at"]
