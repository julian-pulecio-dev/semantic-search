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
    permission_classes = []

    @extend_schema(
        request=SemanticSearchSerializer,
        responses={200: DocumentChunkSerializer(many=True)},
    )
    def post(self, request):
        serializer = SemanticSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query = serializer.validated_data["query"]
        threshold = serializer.validated_data["threshold"]

        embedding = EmbeddingsProcessor().get_embedding(query)

        # CosineDistance ∈ [0, 2]; similarity = 1 − distance.
        # similarity ≥ threshold  ↔  distance ≤ 1 − threshold
        max_distance = 1 - threshold

        chunks = (
            DocumentChunk.objects.filter(embedding__isnull=False)
            .annotate(distance=CosineDistance("embedding", embedding))
            .filter(distance__lte=max_distance)
            .order_by("distance")
        )

        return Response(
            DocumentChunkSerializer(chunks, many=True).data,
            status=status.HTTP_200_OK,
        )
