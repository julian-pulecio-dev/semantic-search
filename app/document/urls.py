from django.urls import path
from .views import (
    CreateDocumentView,
    DeleteDocumentView,
    ListAllDocumentsView,
    ListUserDocumentsView,
    RetrieveDocumentView,
)

app_name = "document"

urlpatterns = [
    path("create/", CreateDocumentView.as_view(), name="create"),
    path("delete/<uuid:pk>/", DeleteDocumentView.as_view(), name="delete"),
    path("list/", ListAllDocumentsView.as_view(), name="list_all"),
    path(
        "retrieve/<uuid:pk>/", RetrieveDocumentView.as_view(), name="retrieve"
    ),
    path("user/list/", ListUserDocumentsView.as_view(), name="list_user"),
]
