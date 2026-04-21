from rest_framework import permissions, generics
from rest_framework_simplejwt.authentication import JWTAuthentication
from document_type.models import DocumentType
from document_type.serializers import DocumentTypeSerializer


class ListAllDocumentTypesView(generics.ListAPIView):
    serializer_class = DocumentTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DocumentType.objects.all()


class ListDocumentTypesView(generics.ListAPIView):
    serializer_class = DocumentTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return DocumentType.objects.all()


class RetrieveDocumentTypeView(generics.RetrieveAPIView):
    serializer_class = DocumentTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return DocumentType.objects.all()


class CreateDocumentTypeView(generics.CreateAPIView):
    serializer_class = DocumentTypeSerializer
    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return DocumentType.objects.all()


class UpdateDocumentTypeView(generics.UpdateAPIView):
    serializer_class = DocumentTypeSerializer
    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return DocumentType.objects.all()


class DeleteDocumentTypeView(generics.DestroyAPIView):
    serializer_class = DocumentTypeSerializer
    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return DocumentType.objects.all()
