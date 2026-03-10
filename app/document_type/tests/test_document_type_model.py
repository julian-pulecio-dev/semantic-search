import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from document_type.models import DocumentType


class DocumentTypeModelTest(TestCase):

    def setUp(self):
        self.document_type = DocumentType.objects.create(
            name="law", authority_score=0.95
        )

    def test_create_document_type(self):
        """
        Test that a DocumentType can be created with valid data and that the
        fields are set correctly.
        """

        self.assertEqual(self.document_type.name, "law")
        self.assertEqual(self.document_type.authority_score, 0.95)
        self.assertIsInstance(self.document_type.id, uuid.UUID)

    def test_unique_name_constraint(self):
        """
        Test that creating a DocumentType with a duplicate name raises an
        IntegrityError.
        """

        with self.assertRaises(IntegrityError):
            DocumentType.objects.create(name="law", authority_score=0.7)

    def test_authority_score_validation_lower_bound(self):
        """
        Test that creating a DocumentType with an authority_score below 0.0 raises
        a ValidationError.
        """

        dt = DocumentType(name="testimony", authority_score=-0.1)
        with self.assertRaises(ValidationError):
            dt.full_clean()

    def test_authority_score_validation_upper_bound(self):
        """
        Test that creating a DocumentType with an authority_score above 1.0
        raises a ValidationError.
        """

        dt = DocumentType(name="regulation", authority_score=1.5)
        with self.assertRaises(ValidationError):
            dt.full_clean()

    def test_default_authority_score(self):
        """Test that the default authority_score is set to 0.5 if not provided."""

        dt = DocumentType.objects.create(name="jurisprudence")
        self.assertEqual(dt.authority_score, 0.5)

    def test_str_representation(self):
        """Test that the string representation of a DocumentType instance is correct."""

        self.assertEqual(str(self.document_type), "law (0.95)")

    def test_metadata_default(self):
        """Test that the default metadata is an empty dictionary."""

        self.assertEqual(self.document_type.metadata, {})

    def test_ordering_by_authority_score_desc(self):
        """
        Test that DocumentType instances are ordered by authority_score in
        descending order.
        """

        DocumentType.objects.create(name="contract", authority_score=0.5)
        first = DocumentType.objects.first()
        self.assertEqual(first.name, "law")
