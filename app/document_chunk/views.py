from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from document_chunk.models import DocumentChunk
from document_chunk.serializers import DocumentChunkSerializer


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
