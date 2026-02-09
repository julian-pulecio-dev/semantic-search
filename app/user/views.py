from django.shortcuts import render
from django.contrib.auth import get_user_model
from rest_framework import generics, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from .serializers import UserSerializer

class BaseUserView:
    serializer_class = UserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class CreateUserView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


class MeView(BaseUserView, generics.RetrieveUpdateDestroyAPIView):
    pass


class ListUsersView(BaseUserView, generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = get_user_model().objects.all()
