from django.urls import path
from .views import (
    DocumentChunkListCreateView,
    DocumentChunkRetrieveUpdateDestroyView,
    ChunkRefreshView,
    ChunkReboundView,
)

urlpatterns = [
    path("", DocumentChunkListCreateView.as_view(), name="chunk-list"),
    path(
        "<uuid:pk>/",
        DocumentChunkRetrieveUpdateDestroyView.as_view(),
        name="chunk-detail",
    ),
    path(
        "<uuid:pk>/refresh/", ChunkRefreshView.as_view(), name="chunk-refresh"
    ),
    path(
        "<uuid:pk>/rebound/", ChunkReboundView.as_view(), name="chunk-rebound"
    ),
]
