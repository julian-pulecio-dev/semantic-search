import os
from rest_framework import permissions, generics
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import DocumentSerializer
from document.models import Document
from document.services.storage import S3FileLoaderService

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")


class ListAllDocumentsView(generics.ListAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return Document.objects.all()


class RetrieveDocumentView(generics.RetrieveAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return Document.objects.all()


class DeleteDocumentView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return Document.objects.all()

    def perform_destroy(self, instance):
        s3_loader = S3FileLoaderService(bucket_name=BUCKET_NAME)
        s3_loader.delete_file(key=instance.s3_key)
        instance.delete()
