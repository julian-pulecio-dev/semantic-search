from django.urls import path
from .views import CreateDocumentView

app_name = "document"

urlpatterns = [
    path("create/", CreateDocumentView.as_view(), name="create"),
]
