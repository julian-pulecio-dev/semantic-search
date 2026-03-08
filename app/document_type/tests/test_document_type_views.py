from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from document_type.models import DocumentType

User = get_user_model()

LIST_URL = reverse("document_type:list")
ADMIN_LIST_URL = reverse("document_type:admin_list")
CREATE_URL = reverse("document_type:create")


def DETAIL_URL(pk):
    return reverse("document_type:detail", args=[pk])


def UPDATE_URL(pk):
    return reverse("document_type:update", args=[pk])


def DELETE_URL(pk):
    return reverse("document_type:delete", args=[pk])


class DocumentTypeViewsTest(APITestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@test.com", password="password", is_staff=True
        )

        self.user = User.objects.create_user(
            email="user@test.com", password="password"
        )

        admin_refresh = RefreshToken.for_user(self.admin)
        user_refresh = RefreshToken.for_user(self.user)

        self.admin_token = str(admin_refresh.access_token)
        self.user_token = str(user_refresh.access_token)

        self.document_type = DocumentType.objects.create(
            name="law", authority_score=0.95
        )

    def authenticate(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_list_document_types_authenticated(self):
        """Test that authenticated users can access the list of document
        types."""

        self.authenticate(self.user_token)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_all_document_types_admin(self):
        """Test that admin users can access the list of all document types."""

        self.authenticate(self.admin_token)
        response = self.client.get(ADMIN_LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_document_type(self):
        """Test that authenticated users can retrieve a specific document type
        by ID."""

        self.authenticate(self.user_token)
        response = self.client.get(DETAIL_URL(self.document_type.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.document_type.id))

    def test_create_document_type_admin(self):
        """Test that admin users can create a new document type."""

        self.authenticate(self.admin_token)

        data = {"name": "contract", "slug": "contract", "authority_score": 0.6}

        response = self.client.post(CREATE_URL, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DocumentType.objects.count(), 2)

    def test_create_document_type_forbidden_for_user(self):
        """Test that non-admin users cannot create a new document type."""

        self.authenticate(self.user_token)

        data = {"name": "contract", "slug": "contract", "authority_score": 0.6}

        response = self.client.post(CREATE_URL, data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_document_type_admin(self):
        """Test that admin users can update an existing document type."""

        self.authenticate(self.admin_token)

        data = {"name": "law_updated", "slug": "law", "authority_score": 0.97}

        response = self.client.patch(UPDATE_URL(self.document_type.id), data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.document_type.refresh_from_db()
        self.assertEqual(self.document_type.name, "law_updated")

    def test_delete_document_type_admin(self):
        """Test that admin users can delete an existing document type."""

        self.authenticate(self.admin_token)

        response = self.client.delete(DELETE_URL(self.document_type.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(DocumentType.objects.count(), 0)

    def test_delete_document_type_forbidden_for_user(self):
        """Test that non-admin users cannot delete a document type."""

        self.authenticate(self.user_token)

        response = self.client.delete(DELETE_URL(self.document_type.id))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
