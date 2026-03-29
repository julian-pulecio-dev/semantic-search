from django.urls import path
from .views import (
    DocumentChunkListView,
    DocumentChunkDetailView,
    SemanticSearchView,
)

urlpatterns = [
    path(
        "documents/<uuid:document_id>/chunks/",
        DocumentChunkListView.as_view(),
        name="document-chunk-list",
    ),
    path(
        "chunks/<uuid:id>/",
        DocumentChunkDetailView.as_view(),
        name="document-chunk-detail",
    ),
    path(
        "search/",
        SemanticSearchView.as_view(),
        name="semantic-search",
    ),
]
