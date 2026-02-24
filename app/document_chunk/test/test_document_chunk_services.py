import unittest
from unittest.mock import MagicMock, patch
from io import BytesIO
import os
from document_chunk.services.document_chunk_processor import (
    DocumentChunkProcessor,
)


class TestDocumentChunkProcessor(unittest.TestCase):

    def setUp(self):
        self.mock_document = MagicMock()
        self.mock_document.id = 1
        self.mock_document.s3_key = "path/to/test.pdf"
        os.environ["S3_BUCKET_NAME"] = "test-bucket"

        with patch("boto3.client"):
            self.processor = DocumentChunkProcessor(self.mock_document)

    @patch("document.views.DocumentChunkProcessor._get_s3_file")
    @patch("document.views.DocumentChunkProcessor._pdf_to_text")
    def test_process_orchestration(self, mock_pdf_to_text, mock_get_s3):
        mock_get_s3.return_value = BytesIO(b"dummy pdf data")
        mock_pdf_to_text.return_value = [
            {"page_number": 1, "text": "Hello world"}
        ]

        results = self.processor.process()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "Hello world")
        self.assertEqual(results[0]["document_id"], 1)

    def test_is_two_column_layout_true(self):
        mock_page = MagicMock()
        mock_page.width = 1000

        words = [
            {"x0": 50, "top": 10, "text": "Left"},
            {"x0": 900, "top": 10, "text": "Right"},
        ]

        result = self.processor._is_two_column_layout(mock_page, words)
        self.assertTrue(result)

    def test_is_two_column_layout_false(self):
        mock_page = MagicMock()
        mock_page.width = 1000

        words = [
            {"x0": 490, "top": 10, "text": "Middle"},
            {"x0": 510, "top": 10, "text": "Middle"},
        ]

        result = self.processor._is_two_column_layout(mock_page, words)
        self.assertFalse(result)

    def test_group_words_into_lines(self):
        words = [
            {"x0": 10, "top": 100, "text": "Hello"},
            {"x0": 50, "top": 102, "text": "World"},
            {"x0": 10, "top": 200, "text": "Next"},
        ]

        lines = self.processor._group_words_into_lines(words)

        self.assertEqual(len(lines), 2)
        first_line_key = list(lines.keys())[0]
        self.assertEqual(len(lines[first_line_key]), 2)

    def test_text_to_chunks(self):
        pages_data = [
            {"page_number": 1, "text": "Este es un texto de prueba."}
        ]

        chunks = self.processor._text_to_chunks(pages_data)

        self.assertIsInstance(chunks, list)
        self.assertEqual(chunks[0]["page_number"], 1)
        self.assertEqual(chunks[0]["document_id"], 1)
        self.assertIn("content", chunks[0])
