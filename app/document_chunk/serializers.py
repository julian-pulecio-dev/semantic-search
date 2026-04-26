from rest_framework import serializers
from document_chunk.models import DocumentChunk


class EmbeddingField(serializers.Field):
    """Read-only field that converts a pgvector VectorField to a plain list."""

    def to_representation(self, value):
        if value is None:
            return None
        return list(value)

    def to_internal_value(self, data):
        raise serializers.ValidationError("Embedding fields are read-only.")


class DocumentChunkSerializer(serializers.ModelSerializer):
    embedding = EmbeddingField(read_only=True)
    embedding_title = EmbeddingField(read_only=True)
    embedding_doc = EmbeddingField(read_only=True)

    class Meta:
        model = DocumentChunk
        fields = [
            "id",
            "document",
            "start_page",
            "end_page",
            "content",
            "section_type",
            "section_title",
            "context_prefix",
            "chunk_index",
            "bounding_polygons",
            "embedding",
            "embedding_title",
            "embedding_doc",
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
