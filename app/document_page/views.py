from rest_framework import generics, permissions
from document_page.models import DocumentPage
from document_page.serializers import DocumentPageSerializer


class DocumentPageListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentPageSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return DocumentPage.objects.filter(document_id=self.kwargs["doc_id"])

    def perform_create(self, serializer):
        serializer.save(document_id=self.kwargs["doc_id"])


class DocumentPageRetrieveUpdateDestroyView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = DocumentPageSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return DocumentPage.objects.filter(document_id=self.kwargs["doc_id"])
