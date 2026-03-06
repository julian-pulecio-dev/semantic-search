import os
from rest_framework import permissions
from document.services.storage import S3FileLoaderService
from upload_session.services.document_upload_service import (
    DocumentUploadService,
)
from upload_session.serializers import UploadSessionSerializer

from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.views import APIView
from rest_framework import status

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")


class CreateUploadSessionView(APIView):
    parser_classes = []
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        storage_service = S3FileLoaderService(bucket_name=BUCKET_NAME)
        document_service = DocumentUploadService(
            user=request.user, storage=storage_service
        )
        response_data = document_service.create_upload_request()
        serializer = UploadSessionSerializer(response_data)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
