from django.urls import path
from .views import CreateUserView, MeView, ListUsersView

app_name = "user"

urlpatterns = [
    path("create/", CreateUserView.as_view(), name="create"),
    path("me", MeView.as_view(), name="me"),
    path("list/", ListUsersView.as_view(), name="list"),
]