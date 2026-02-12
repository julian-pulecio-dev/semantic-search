from rest_framework import permissions
from .serializers import DocumentSerializer
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework.response import Response
from document.services.storage import upload_file_to_s3
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import generics
from rest_framework import serializers


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
        serializer = DocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data["file"]
        url = upload_file_to_s3(file, key=f"{request.user.email}/{file.name}")
        document = request.user.documents.create(url=url)

        return Response({"url": document.url}, status=201)
