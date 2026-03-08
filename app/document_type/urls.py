from django.urls import path

from document_type.views import (
    ListAllDocumentTypesView,
    ListDocumentTypesView,
    RetrieveDocumentTypeView,
    CreateDocumentTypeView,
    UpdateDocumentTypeView,
    DeleteDocumentTypeView,
)

app_name = "document_type"

urlpatterns = [
    path("list/", ListAllDocumentTypesView.as_view(), name="admin_list"),
    path("user/list/", ListDocumentTypesView.as_view(), name="list"),
    path(
        "retrieve/<uuid:pk>/",
        RetrieveDocumentTypeView.as_view(),
        name="detail",
    ),
    path("create/", CreateDocumentTypeView.as_view(), name="create"),
    path("update/<uuid:pk>/", UpdateDocumentTypeView.as_view(), name="update"),
    path("delete/<uuid:pk>/", DeleteDocumentTypeView.as_view(), name="delete"),
]
