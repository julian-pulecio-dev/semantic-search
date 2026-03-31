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
            "bounding_polygons",
            "created_at",
            "embedding",
        ]
        read_only_fields = fields


class SemanticSearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    top_k = serializers.IntegerField(min_value=1, max_value=50, default=5)
