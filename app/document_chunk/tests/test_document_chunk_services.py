import unittest
from unittest.mock import MagicMock, patch
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

    def test_process_orchestration(self):
        self.processor.pdf_extractor = MagicMock()
        self.processor.pdf_extractor.extract.return_value = [
            {"page_number": 1, "text": "Hello world", "words": []}
        ]
        self.processor.bounding_polygon_resolver = MagicMock()
        self.processor.bounding_polygon_resolver.resolve.return_value = ([], {})

        batches = self.processor.process()

        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 1)
        self.assertEqual(batches[0][0].content, "Hello world")
        self.assertEqual(batches[0][0].document_id, 1)

    def test_text_to_chunks(self):
        pages_data = [
            {"page_number": 1, "text": "Este es un texto de prueba.", "words": []}
        ]
        self.processor.bounding_polygon_resolver = MagicMock()
        self.processor.bounding_polygon_resolver.resolve.return_value = ([], {})

        chunks = self.processor._text_to_chunks(pages_data)

        self.assertIsInstance(chunks, list)
        self.assertEqual(chunks[0].document_id, 1)
        self.assertIsNotNone(chunks[0].content)
