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
    DocumentChunkListSerializer,
    ChunkRefreshSerializer,
    ChunkReboundSerializer,
    SemanticSearchSerializer,
    SemanticSearchResultSerializer,
)
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
from document_chunk.services.chunk_refresh_service import ChunkRefreshService
from document_chunk.services.reranker_service import RerankerService
from document_page.models import DocumentPage


class DocumentChunkListCreateView(generics.ListCreateAPIView):
    permission_classes = []

    def get_serializer_class(self):
        if self.request.method == "GET":
            return DocumentChunkListSerializer
        return DocumentChunkSerializer

    def get_queryset(self):
        return (
            DocumentChunk.objects.select_related("start_page", "end_page")
            .filter(document_id=self.kwargs["doc_id"])
            .order_by("chunk_index")
        )

    def perform_create(self, serializer):
        serializer.save(document_id=self.kwargs["doc_id"])


class DocumentChunkRetrieveUpdateDestroyView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = DocumentChunkSerializer
    permission_classes = []

    def get_queryset(self):
        return DocumentChunk.objects.filter(document_id=self.kwargs["doc_id"])


class ChunkRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChunkRefreshSerializer,
        responses={200: DocumentChunkSerializer},
    )
    def patch(self, request, doc_id, pk):
        chunk = generics.get_object_or_404(
            DocumentChunk, id=pk, document_id=doc_id
        )

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


class ChunkReboundView(APIView):
    """
    Re-extracts text and reprocesses a chunk using new bounding polygons,
    start page, and end page.

    Updates: content, section metadata, all embeddings, bounding_polygons,
    start_page, end_page.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChunkReboundSerializer,
        responses={200: DocumentChunkSerializer},
    )
    def patch(self, request, doc_id, pk):
        chunk = generics.get_object_or_404(
            DocumentChunk.objects.select_related(
                "start_page__document", "end_page"
            ),
            id=pk,
            document_id=doc_id,
        )

        serializer = ChunkReboundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        start_page = generics.get_object_or_404(
            DocumentPage,
            id=serializer.validated_data["start_page"],
            document_id=doc_id,
        )
        end_page = generics.get_object_or_404(
            DocumentPage,
            id=serializer.validated_data["end_page"],
            document_id=doc_id,
        )

        chunk = ChunkRefreshService().refresh(
            chunk=chunk,
            bounding_polygons=serializer.validated_data["bounding_polygons"],
            start_page=start_page,
            end_page=end_page,
        )

        return Response(
            DocumentChunkSerializer(chunk).data,
            status=status.HTTP_200_OK,
        )


_RERANK_CANDIDATE_MULTIPLIER = 3


class SemanticSearchView(APIView):
    """
    Hybrid semantic search over document chunks with optional reranking.

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
    4. If rerank=True, retrieve k * 3 candidates and run them through
       Amazon Bedrock's reranking model before returning the top k.
       The response includes both similarity (cosine-based) and rerank_score.
    5. Return the top-k chunks ordered by the combined score (or rerank score).
    """

    permission_classes = []

    @extend_schema(
        request=SemanticSearchSerializer,
        responses={200: SemanticSearchResultSerializer(many=True)},
    )
    def post(self, request):
        serializer = SemanticSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query: str = serializer.validated_data["query"]
        k: int = serializer.validated_data["k"]
        rerank: bool = serializer.validated_data["rerank"]

        query_embedding = EmbeddingsProcessor().get_embedding(query)
        keyword_boost = self._keyword_boost(query)

        candidate_k = k * _RERANK_CANDIDATE_MULTIPLIER if rerank else k

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
            .order_by("score")[:candidate_k]
        )

        if rerank:
            chunks = RerankerService().rerank(query, list(chunks), top_n=k)

        return Response(
            SemanticSearchResultSerializer(chunks, many=True).data,
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
