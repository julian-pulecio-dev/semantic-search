import os
from rest_framework import generics, permissions
from document_page.models import DocumentPage
from document_page.serializers import DocumentPageSerializer
from document.services.storage import S3FileLoaderService

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")


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

    def perform_destroy(self, instance):
        if instance.s3_key:
            s3_loader = S3FileLoaderService(bucket_name=BUCKET_NAME)
            s3_loader.delete_file(key=instance.s3_key)
        instance.delete()
