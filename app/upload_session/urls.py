from django.urls import path
from .views import CreateUploadSessionView, UploadSessionDetailView

app_name = "upload_session"

urlpatterns = [
    path("create/", CreateUploadSessionView.as_view(), name="create"),
    path("<uuid:id>/", UploadSessionDetailView.as_view(), name="detail"),
]
