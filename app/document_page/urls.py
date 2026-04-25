from django.urls import path
from .views import (
    DocumentPageListCreateView,
    DocumentPageRetrieveUpdateDestroyView,
)

urlpatterns = [
    path("", DocumentPageListCreateView.as_view(), name="page-list"),
    path(
        "<uuid:pk>/",
        DocumentPageRetrieveUpdateDestroyView.as_view(),
        name="page-detail",
    ),
]
