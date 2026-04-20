from django.urls import path, include
from .views import (
    DocumentPageListCreateView,
    DocumentPageRetrieveUpdateDestroyView,
)
import document_chunk.urls as chunk_urls

urlpatterns = [
    path("", DocumentPageListCreateView.as_view(), name="page-list"),
    path(
        "<uuid:pk>/",
        DocumentPageRetrieveUpdateDestroyView.as_view(),
        name="page-detail",
    ),
    path("<uuid:page_id>/chunks/", include(chunk_urls)),
]
