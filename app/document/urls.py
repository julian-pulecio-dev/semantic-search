from django.urls import path
from .views import (
    DeleteDocumentView,
    ListAllDocumentsView,
    RetrieveDocumentView,
)

app_name = "document"

urlpatterns = [
    path("list/", ListAllDocumentsView.as_view(), name="list_all"),
    path(
        "retrieve/<uuid:pk>/", RetrieveDocumentView.as_view(), name="retrieve"
    ),
    path("delete/<uuid:pk>/", DeleteDocumentView.as_view(), name="delete"),
]
