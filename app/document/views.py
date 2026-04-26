import os
from rest_framework import permissions, generics
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import DocumentSerializer
from document.models import Document
from document.services.storage import S3FileLoaderService

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")


class DocumentListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(status=Document.Status.PENDING, user=self.request.user)


class DocumentRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return Document.objects.all()

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

    def perform_destroy(self, instance):
        if instance.s3_key:
            s3_loader = S3FileLoaderService(bucket_name=BUCKET_NAME)
            s3_loader.delete_file(key=instance.s3_key)
        instance.delete()
