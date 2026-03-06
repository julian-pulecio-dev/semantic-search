import os
from rest_framework import permissions
from .serializers import DocumentSerializer
from document.models import Document
from document.services.storage import S3FileLoaderService
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import generics

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")


class ListAllDocumentsView(generics.ListAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return Document.objects.all()


class ListUserDocumentsView(generics.ListAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return self.request.user.documents.all()


class RetrieveDocumentView(generics.RetrieveAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Document.objects.all()
        return user.documents.all()


class DeleteDocumentView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return self.request.user.documents.all()

    def perform_destroy(self, instance):
        s3_loader = S3FileLoaderService(bucket_name=BUCKET_NAME)
        s3_loader.delete_file(key=instance.s3_key)
        instance.delete()
