import os
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.parsers import JSONParser
from drf_spectacular.utils import extend_schema
from document.services.storage import S3FileLoaderService
from upload_session.models import UploadSession
from upload_session.services.document_upload_service import (
    DocumentUploadService,
)
from upload_session.serializers import (
    UploadSessionSerializer,
    UploadSessionDetailSerializer,
    CreateUploadSessionSerializer,
)

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")


class UploadSessionDetailView(generics.RetrieveAPIView):
    serializer_class = UploadSessionDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    lookup_field = "id"

    def get_queryset(self):
        return UploadSession.objects.filter(user=self.request.user)


class CreateUploadSessionView(APIView):
    parser_classes = [JSONParser]
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    @extend_schema(
        request=CreateUploadSessionSerializer,
        responses={201: UploadSessionSerializer},
    )
    def post(self, request):
        input_serializer = CreateUploadSessionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        document_type = input_serializer.validated_data["document_type"]

        storage_service = S3FileLoaderService(bucket_name=BUCKET_NAME)
        document_service = DocumentUploadService(
            user=request.user, storage=storage_service
        )
        response_data = document_service.create_upload_request(
            document_type=document_type
        )
        serializer = UploadSessionSerializer(response_data)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
