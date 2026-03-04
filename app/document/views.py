import os
from rest_framework import permissions
from .serializers import DocumentSerializer
from document.models import Document, DocumentStatus
from document.services.storage import S3FileLoader
from document.services.ingestion import create_document_request
from document.serializers import DocumentPresignedURLSerializer

from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework import status

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")


class CreateDocumentView(APIView):
    parser_classes = []
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        response_data = create_document_request(request.user)
        serializer = DocumentPresignedURLSerializer(response_data)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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
        s3_loader = S3FileLoader(bucket_name=BUCKET_NAME)
        s3_loader.delete_file(key=instance.s3_key)
        instance.delete()
