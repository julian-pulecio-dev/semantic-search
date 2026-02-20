from django.test import TestCase
from django.contrib.auth import get_user_model


class DocumentModelTest(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email="test_user@email.com", password="user_password123*"
        )

    def test_create_document_successfully(self):
        document = self.user.documents.create(
            url="https://example.com/document.pdf"
        )
        self.assertEqual(1, self.user.documents.count())
        self.assertEqual(document.url, "https://example.com/document.pdf")
        self.assertEqual(document.user, self.user)
