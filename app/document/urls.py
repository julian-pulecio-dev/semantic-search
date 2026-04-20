from django.urls import path, include
from .views import DocumentListCreateView, DocumentRetrieveUpdateDestroyView
import document_page.urls as page_urls

app_name = "document"

urlpatterns = [
    path("", DocumentListCreateView.as_view(), name="document-list"),
    path(
        "<uuid:pk>/",
        DocumentRetrieveUpdateDestroyView.as_view(),
        name="document-detail",
    ),
    path("<uuid:doc_id>/pages/", include(page_urls)),
]
