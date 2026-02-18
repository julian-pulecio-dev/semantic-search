from rest_framework import permissions
from .serializers import CreateDocumentSerializer, DocumentSerializer
from core.models import Document
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework.response import Response
from document.services.storage import upload_file_to_s3, delete_file_from_s3
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import generics
from rest_framework import serializers
from uuid import uuid4


class CreateDocumentView(generics.CreateAPIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    @extend_schema(
        operation_id="upload_document",
        request=inline_serializer(
            name="InlineDocumentSerializer",
            fields={
                "file": serializers.FileField(),
            },
        ),
        responses={
            201: inline_serializer(
                name="Success", fields={"msg": serializers.CharField()}
            )
        },
    )
    def post(self, request):
        serializer = CreateDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data["file"]
        file_extension = file.name.split(".")[-1]

        uuid4_str = str(uuid4())
        key = f"{request.user.email}/{uuid4_str}.{file_extension}"
        url = upload_file_to_s3(file, key=key)
        document = request.user.documents.create(url=url, s3_key=key)

        return Response({"url": document.url}, status=201)


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
        delete_file_from_s3(key=instance.s3_key)
        instance.delete()
