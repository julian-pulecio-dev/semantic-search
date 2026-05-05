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


class DocumentChunkListSerializer(serializers.ModelSerializer):
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


class SemanticSearchResultSerializer(DocumentChunkSerializer):
    similarity = serializers.SerializerMethodField()
    rerank_score = serializers.SerializerMethodField()

    class Meta(DocumentChunkSerializer.Meta):
        fields = DocumentChunkSerializer.Meta.fields + [
            "similarity",
            "rerank_score",
        ]

    def get_similarity(self, obj):
        score = getattr(obj, "score", None)
        if score is None:
            return None
        return round(1 - score, 6)

    def get_rerank_score(self, obj):
        score = getattr(obj, "rerank_score", None)
        if score is None:
            return None
        return round(score, 6)


class ChunkReboundSerializer(serializers.Serializer):
    bounding_polygons = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )
    start_page = serializers.UUIDField()
    end_page = serializers.UUIDField()


class SemanticSearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    k = serializers.IntegerField(min_value=1, max_value=100, default=10)
    rerank = serializers.BooleanField(default=False)
