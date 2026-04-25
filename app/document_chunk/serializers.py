from rest_framework import serializers
from document_chunk.models import DocumentChunk


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = [
            "id",
            "document",
            "start_page",
            "end_page",
            "content",
            "section_title",
            "context_prefix",
            "chunk_index",
            "bounding_polygons",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "document",
            "start_page",
            "end_page",
            "created_at",
        ]


class ChunkRefreshSerializer(serializers.Serializer):
    bounding_polygons = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )


class SemanticSearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    k = serializers.IntegerField(min_value=1, max_value=100, default=10)
