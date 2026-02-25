from rest_framework import serializers
from document_chunk.models import DocumentChunk


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = [
            "id",
            "document",
            "content",
            "chunk_index",
            "created_at",
        ]
        read_only_fields = fields
