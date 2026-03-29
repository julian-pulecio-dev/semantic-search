from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from pgvector.django import CosineDistance
from drf_spectacular.utils import extend_schema
from document_chunk.models import DocumentChunk
from document_chunk.serializers import (
    DocumentChunkSerializer,
    SemanticSearchSerializer,
)
from document_chunk.services.embeddings_processor import EmbeddingsProcessor


class DocumentChunkListView(generics.ListAPIView):
    serializer_class = DocumentChunkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        document_id = self.kwargs["document_id"]

        return (
            DocumentChunk.objects.select_related("document")
            .filter(document_id=document_id, document__user=self.request.user)
            .order_by("chunk_index")
        )


class DocumentChunkDetailView(generics.RetrieveAPIView):
    serializer_class = DocumentChunkSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return DocumentChunk.objects.filter(document__user=self.request.user)


class SemanticSearchView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SemanticSearchSerializer,
        responses={200: DocumentChunkSerializer(many=True)},
    )
    def post(self, request):
        serializer = SemanticSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query = serializer.validated_data["query"]
        top_k = serializer.validated_data["top_k"]

        embedding = EmbeddingsProcessor().get_embedding(query)

        chunks = (
            DocumentChunk.objects.filter(
                document__user=request.user,
                embedding__isnull=False,
            )
            .annotate(distance=CosineDistance("embedding", embedding))
            .order_by("distance")[:top_k]
        )

        return Response(
            DocumentChunkSerializer(chunks, many=True).data,
            status=status.HTTP_200_OK,
        )
