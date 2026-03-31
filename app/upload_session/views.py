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
from upload_session.services.upload_session_service import (
    UploadSessionService,
)
from upload_session.serializers import (
    UploadSessionSerializer,
    UploadSessionDetailSerializer,
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
    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JWTAuthentication]

    @extend_schema(
        responses={201: UploadSessionSerializer},
    )
    def post(self, request):
        storage_service = S3FileLoaderService(bucket_name=BUCKET_NAME)
        upload_session_service = UploadSessionService(
            user=request.user, storage=storage_service
        )
        response_data = upload_session_service.create_upload_session()
        serializer = UploadSessionSerializer(response_data)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
