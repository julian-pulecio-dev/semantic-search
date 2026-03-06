from django.urls import path
from .views import CreateUploadSessionView

app_name = "upload_session"

urlpatterns = [
    path("create/", CreateUploadSessionView.as_view(), name="create"),
]
