from django.shortcuts import render
from rest_framework import generics, permissions
from .serializers import DocumentSerializer


class CreateDocumentView(generics.CreateAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
