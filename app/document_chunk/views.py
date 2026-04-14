from django.db.models import (
    Case,
    ExpressionWrapper,
    FloatField,
    F,
    Q,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from pgvector.django import CosineDistance
from drf_spectacular.utils import extend_schema
from document_chunk.models import DocumentChunk
from document_chunk.serializers import (
    DocumentChunkSerializer,
    ChunkRefreshSerializer,
    SemanticSearchSerializer,
)
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
from document_chunk.services.chunk_refresh_service import ChunkRefreshService


class DocumentChunkListView(generics.ListAPIView):
    serializer_class = DocumentChunkSerializer
    permission_classes = []

    def get_queryset(self):
        document_id = self.kwargs["document_id"]

        return (
            DocumentChunk.objects.select_related("document")
            .filter(document_id=document_id)
            .order_by("chunk_index")
        )


class DocumentChunkDetailView(generics.RetrieveAPIView):
    serializer_class = DocumentChunkSerializer
    permission_classes = []
    lookup_field = "id"

    def get_queryset(self):
        return DocumentChunk.objects.all()


class ChunkRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChunkRefreshSerializer,
        responses={200: DocumentChunkSerializer},
    )
    def patch(self, request, id):
        chunk = generics.get_object_or_404(DocumentChunk, id=id)

        serializer = ChunkRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        chunk = ChunkRefreshService().refresh(
            chunk=chunk,
            bounding_polygons=serializer.validated_data["bounding_polygons"],
        )

        return Response(
            DocumentChunkSerializer(chunk).data,
            status=status.HTTP_200_OK,
        )


class SemanticSearchView(APIView):
    """
    Hybrid semantic search over document chunks.

    Strategy
    --------
    1. Embed the query with the same model used at ingestion time.
    2. Annotate each chunk with three cosine distances:
         d_chunk  — distance to the full contextual chunk embedding  (weight 0.5)
         d_title  — distance to the section-title embedding          (weight 0.3)
         d_doc    — distance to the document-level embedding         (weight 0.2)
       Null embeddings fall back to the worst-case distance (1.0).
    3. Apply an optional keyword boost: chunks whose content contains any
       significant query term get a −0.05 bonus on the combined score
       (lower distance = better match).
    4. Return the top-k chunks ordered by the combined score.
    """

    permission_classes = []

    @extend_schema(
        request=SemanticSearchSerializer,
        responses={200: DocumentChunkSerializer(many=True)},
    )
    def post(self, request):
        serializer = SemanticSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query: str = serializer.validated_data["query"]
        k: int = serializer.validated_data["k"]

        query_embedding = EmbeddingsProcessor().get_embedding(query)

        keyword_boost = self._keyword_boost(query)

        chunks = (
            DocumentChunk.objects.filter(embedding__isnull=False)
            .annotate(
                d_chunk=CosineDistance("embedding", query_embedding),
                d_title=Coalesce(
                    CosineDistance("embedding_title", query_embedding),
                    Value(1.0),
                ),
                d_doc=Coalesce(
                    CosineDistance("embedding_doc", query_embedding),
                    Value(1.0),
                ),
            )
            .annotate(
                score=ExpressionWrapper(
                    F("d_chunk") * 0.5
                    + F("d_title") * 0.3
                    + F("d_doc") * 0.2
                    + keyword_boost,
                    output_field=FloatField(),
                )
            )
            .order_by("score")[:k]
        )

        return Response(
            DocumentChunkSerializer(chunks, many=True).data,
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _keyword_boost(query: str):
        """
        Returns a Case expression that subtracts 0.05 from the score when
        the chunk content contains any meaningful term from the query.
        A lower score means a better match (distance semantics).
        """
        terms = [t.lower() for t in query.split() if len(t) > 3]
        if not terms:
            return Value(0.0, output_field=FloatField())

        keyword_q = Q()
        for term in terms:
            keyword_q |= Q(content__icontains=term)

        return Case(
            When(keyword_q, then=Value(-0.05)),
            default=Value(0.0),
            output_field=FloatField(),
        )
