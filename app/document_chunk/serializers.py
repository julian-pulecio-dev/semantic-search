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


class ChunkRefreshSerializer(serializers.Serializer):
    bounding_polygons = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )


class SemanticSearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    threshold = serializers.FloatField(
        min_value=0.0, max_value=1.0, default=0.8
    )
