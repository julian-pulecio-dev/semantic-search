import os
import unittest
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.contrib.auth import get_user_model

from document.models import Document
from document_page.models import DocumentPage
from document_chunk.models import DocumentChunk
from document_chunk.services.page_chunk_processor import (
    ArticleSplitter,
    Chunk,
    PageChunkProcessor,
    _extract_section_context,
    _doc_context_text,
)
from document_chunk.services.chunk_bounding_polygon import PagePolygon
from document_chunk.services.exceptions.embedding_exceptions import (
    EmbeddingError,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(
    user, status=Document.Status.PENDING, s3_key="docs/test.pdf"
):
    return Document.objects.create(user=user, status=status, s3_key=s3_key)


def _make_page(document, s3_key="pages/1/pages/page_3.pdf"):
    return DocumentPage.objects.create(document=document, s3_key=s3_key)


def _make_processor(page, document, **overrides):
    resolver = MagicMock()
    resolver.resolve.return_value = ([], {})
    defaults = dict(
        pdf_extractor=MagicMock(),
        splitter=MagicMock(),
        bounding_polygon_resolver=resolver,
        embedding_processor=MagicMock(),
    )
    defaults.update(overrides)
    return PageChunkProcessor(page=page, document=document, **defaults)


# ---------------------------------------------------------------------------
# Pure unit tests (no DB)
# ---------------------------------------------------------------------------


class TestChunk(unittest.TestCase):
    def test_chunk_is_immutable(self):
        chunk = Chunk(content="text", chunk_index=0, document_id=1)
        with self.assertRaises((AttributeError, TypeError)):
            chunk.content = "other"

    def test_to_dict_contains_all_fields(self):
        chunk = Chunk(
            content="text",
            chunk_index=0,
            document_id=1,
            section_type="Sentencia",
            section_title="Titulo",
            context_prefix="[Sentencia] Titulo",
            bounding_polygons=[{"page_number": 1, "points": []}],
        )
        d = chunk.to_dict()
        self.assertEqual(d["content"], "text")
        self.assertEqual(d["section_type"], "Sentencia")
        self.assertEqual(d["context_prefix"], "[Sentencia] Titulo")


class TestExtractSectionContext(unittest.TestCase):
    def test_returns_known_keyword_label(self):
        section_type, _ = _extract_section_context(
            "Esta es una sentencia del juez."
        )
        self.assertEqual(section_type, "Sentencia")

    def test_defaults_to_legal_when_no_keyword(self):
        section_type, _ = _extract_section_context(
            "Texto genérico sin palabras clave."
        )
        self.assertEqual(section_type, "Legal")

    def test_section_title_is_first_non_empty_line(self):
        _, section_title = _extract_section_context(
            "\n\nPrimera Línea\nSegunda"
        )
        self.assertEqual(section_title, "Primera Línea")

    def test_section_title_truncated_to_200_chars(self):
        long_line = "x" * 300
        _, section_title = _extract_section_context(long_line)
        self.assertEqual(len(section_title), 200)


class TestDocContextText(unittest.TestCase):
    def test_returns_document_name_from_s3_key(self):
        doc = MagicMock()
        doc.s3_key = "docs/mi_contrato.pdf"
        self.assertEqual(
            _doc_context_text(doc), "Documento legal: mi contrato"
        )

    def test_replaces_underscores_and_hyphens_with_spaces(self):
        doc = MagicMock()
        doc.s3_key = "docs/mi_contrato-2024.pdf"
        self.assertIn("mi contrato 2024", _doc_context_text(doc))

    def test_returns_generic_when_key_is_none(self):
        doc = MagicMock()
        doc.s3_key = None
        self.assertEqual(_doc_context_text(doc), "Documento legal")


class TestArticleSplitter(unittest.TestCase):
    def test_splits_on_articulo_boundary(self):
        text = (
            "Preamble\nArtículo 1. First article.\nArtículo 2. Second article."
        )
        chunks = ArticleSplitter().split_text(text)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(chunks[1].startswith("Artículo 1"))
        self.assertTrue(chunks[2].startswith("Artículo 2"))

    def test_preamble_returned_as_first_chunk(self):
        text = "Preamble text\nArtículo 1. Content."
        chunks = ArticleSplitter().split_text(text)
        self.assertEqual(chunks[0], "Preamble text")

    def test_text_without_articles_returned_as_single_chunk(self):
        self.assertEqual(
            ArticleSplitter().split_text("Just some text."),
            ["Just some text."],
        )

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(ArticleSplitter().split_text(""), [])

    def test_case_insensitive_articulo(self):
        text = "ARTÍCULO 1. Mayúsculas.\nArticulo 2. Minúsculas."
        chunks = ArticleSplitter().split_text(text)
        self.assertEqual(len(chunks), 2)


class TestPageChunkProcessorPageNumberFromKey(unittest.TestCase):
    def _processor_with_key(self, s3_key):
        page = MagicMock()
        page.s3_key = s3_key
        proc = PageChunkProcessor.__new__(PageChunkProcessor)
        proc.page = page
        return proc

    def test_extracts_page_number(self):
        self.assertEqual(
            self._processor_with_key(
                "pages/1/pages/page_3.pdf"
            )._page_number_from_key(),
            3,
        )

    def test_extracts_multi_digit_page_number(self):
        self.assertEqual(
            self._processor_with_key(
                "pages/42/pages/page_12.pdf"
            )._page_number_from_key(),
            12,
        )


# ---------------------------------------------------------------------------
# DB-backed tests
# ---------------------------------------------------------------------------


class TestPageChunkProcessorInit(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="pw"
        )
        self.document = _make_document(self.user)
        self.page = _make_page(self.document)

    def test_post_init_sets_document_status_to_processing(self):
        _make_processor(self.page, self.document)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSING)

    def test_post_init_creates_default_dependencies_when_not_provided(self):
        with (
            patch(
                "document_chunk.services.page_chunk_processor.PDFTextExtractor"
            ),
            patch(
                "document_chunk.services.page_chunk_processor.ArticleSplitter"
            ),
            patch(
                "document_chunk.services.page_chunk_processor.ChunkBoundingPolygon"
            ),
            patch(
                "document_chunk.services.page_chunk_processor.EmbeddingsProcessor"
            ),
        ):
            processor = PageChunkProcessor(
                page=self.page, document=self.document
            )
        self.assertIsNotNone(processor.pdf_extractor)
        self.assertIsNotNone(processor.splitter)
        self.assertIsNotNone(processor.bounding_polygon_resolver)
        self.assertIsNotNone(processor.embedding_processor)


class TestPageChunkProcessorTextToChunks(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="pw"
        )
        self.document = _make_document(self.user)
        self.page = _make_page(self.document)
        self.mock_splitter = MagicMock()
        self.mock_resolver = MagicMock()
        self.mock_resolver.resolve.return_value = ([], {})

    def _processor(self):
        return PageChunkProcessor(
            page=self.page,
            document=self.document,
            pdf_extractor=MagicMock(),
            splitter=self.mock_splitter,
            bounding_polygon_resolver=self.mock_resolver,
            embedding_processor=MagicMock(),
        )

    def test_calls_split_text_on_full_document_text(self):
        self.mock_splitter.split_text.return_value = ["chunk 1"]
        self._processor()._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )
        self.mock_splitter.split_text.assert_called_once_with("some text")

    def test_concatenates_pages_with_double_newline(self):
        self.mock_splitter.split_text.return_value = ["text"]
        self._processor()._text_to_chunks(
            [
                {"page_number": 1, "text": "page one", "words": []},
                {"page_number": 2, "text": "page two", "words": []},
            ]
        )
        self.mock_splitter.split_text.assert_called_once_with(
            "page one\n\npage two"
        )

    def test_returns_chunk_for_each_split(self):
        self.mock_splitter.split_text.return_value = ["chunk 1", "chunk 2"]
        chunks = self._processor()._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].content, "chunk 1")
        self.assertEqual(chunks[1].content, "chunk 2")

    def test_assigns_correct_document_id(self):
        self.mock_splitter.split_text.return_value = ["text"]
        chunks = self._processor()._text_to_chunks(
            [{"page_number": 1, "text": "text", "words": []}]
        )
        self.assertEqual(chunks[0].document_id, self.document.id)

    def test_assigns_start_and_end_page(self):
        self.mock_splitter.split_text.return_value = ["text"]
        chunks = self._processor()._text_to_chunks(
            [{"page_number": 1, "text": "text", "words": []}]
        )
        self.assertEqual(chunks[0].start_page, self.page)
        self.assertEqual(chunks[0].end_page, self.page)

    def test_bounding_polygons_stored_in_chunk(self):
        self.mock_splitter.split_text.return_value = ["chunk 1"]
        polygon = PagePolygon(
            page_number=2, points=[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]
        )
        self.mock_resolver.resolve.return_value = ([polygon], {})
        chunks = self._processor()._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )
        self.assertEqual(
            chunks[0].bounding_polygons,
            [
                {
                    "page_number": 2,
                    "points": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                }
            ],
        )

    def test_bounding_polygons_empty_when_no_polygons(self):
        self.mock_splitter.split_text.return_value = ["chunk 1"]
        chunks = self._processor()._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )
        self.assertEqual(chunks[0].bounding_polygons, [])

    def test_page_cursors_passed_across_chunks(self):
        self.mock_splitter.split_text.return_value = ["chunk 1", "chunk 2"]
        first_cursors = {1: 5}
        self.mock_resolver.resolve.side_effect = [
            ([], first_cursors),
            ([], {1: 10}),
        ]
        self._processor()._text_to_chunks(
            [{"page_number": 1, "text": "some text", "words": []}]
        )
        calls = self.mock_resolver.resolve.call_args_list
        self.assertEqual(calls[1].kwargs["page_cursors"], first_cursors)

    def test_sets_section_type_on_chunk(self):
        self.mock_splitter.split_text.return_value = ["sentencia del tribunal"]
        chunks = self._processor()._text_to_chunks(
            [{"page_number": 1, "text": "sentencia", "words": []}]
        )
        self.assertEqual(chunks[0].section_type, "Sentencia")

    def test_sets_context_prefix_on_chunk(self):
        self.mock_splitter.split_text.return_value = ["sentencia del tribunal"]
        chunks = self._processor()._text_to_chunks(
            [{"page_number": 1, "text": "sentencia", "words": []}]
        )
        self.assertTrue(chunks[0].context_prefix.startswith("[Sentencia]"))


class TestPageChunkProcessorPersistChunks(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="pw"
        )
        self.document = _make_document(self.user)
        self.page = _make_page(self.document)

    def _chunk(self, index=0):
        return Chunk(
            content=f"chunk {index}",
            chunk_index=index,
            document_id=self.document.id,
            section_type="Legal",
            section_title="Titulo",
            context_prefix="[Legal] Titulo",
            bounding_polygons=[],
            start_page=self.page,
            end_page=self.page,
        )

    def test_creates_db_chunks(self):
        processor = _make_processor(self.page, self.document)
        db_chunks = processor._persist_chunks([self._chunk(0), self._chunk(1)])
        self.assertEqual(len(db_chunks), 2)
        self.assertEqual(
            DocumentChunk.objects.filter(document=self.document).count(), 2
        )

    def test_assigns_sequential_global_indices(self):
        processor = _make_processor(self.page, self.document)
        db_chunks = processor._persist_chunks([self._chunk(0), self._chunk(1)])
        self.assertEqual(db_chunks[0].chunk_index, 0)
        self.assertEqual(db_chunks[1].chunk_index, 1)

    def test_continues_index_from_existing_max(self):
        DocumentChunk.objects.create(
            document=self.document,
            content="existing",
            chunk_index=3,
            start_page=self.page,
            end_page=self.page,
        )
        processor = _make_processor(self.page, self.document)
        db_chunks = processor._persist_chunks([self._chunk(0)])
        self.assertEqual(db_chunks[0].chunk_index, 4)


class TestPageChunkProcessorAttachEmbeddings(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="pw"
        )
        self.document = _make_document(
            self.user, s3_key="docs/mi_contrato.pdf"
        )
        self.page = _make_page(self.document)
        self.mock_embedder = MagicMock()

    def _chunk_in_db(self, index=0):
        return DocumentChunk.objects.create(
            document=self.document,
            content="texto",
            chunk_index=index,
            context_prefix="[Legal] Titulo",
            start_page=self.page,
            end_page=self.page,
        )

    def _processor(self):
        return PageChunkProcessor(
            page=self.page,
            document=self.document,
            pdf_extractor=MagicMock(),
            splitter=MagicMock(),
            bounding_polygon_resolver=MagicMock(),
            embedding_processor=self.mock_embedder,
        )

    def _ok_result(self):
        result = MagicMock()
        result.embeddings = [[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]
        result.has_errors.return_value = False
        return result

    def test_calls_embed_batch_with_three_texts(self):
        self.mock_embedder.embed_batch.return_value = self._ok_result()
        self._processor()._attach_embeddings(self._chunk_in_db())
        texts = self.mock_embedder.embed_batch.call_args[0][0]
        self.assertEqual(len(texts), 3)

    def test_saves_embeddings_on_chunk(self):
        result = self._ok_result()
        self.mock_embedder.embed_batch.return_value = result
        chunk = self._chunk_in_db()
        self._processor()._attach_embeddings(chunk)
        self.assertEqual(chunk.embedding, result.embeddings[0])
        self.assertEqual(chunk.embedding_title, result.embeddings[1])
        self.assertEqual(chunk.embedding_doc, result.embeddings[2])

    def test_does_not_raise_on_embedding_error(self):
        self.mock_embedder.embed_batch.side_effect = EmbeddingError("fail")
        self._processor()._attach_embeddings(
            self._chunk_in_db()
        )  # must not raise


class TestPageChunkProcessorFinalizeDocument(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="pw"
        )
        self.document = _make_document(self.user)
        self.page = _make_page(self.document)

    def test_increments_number_of_pages_processed(self):
        self.document.number_of_pages = 2
        self.document.number_of_pages_processed = 0
        self.document.save()
        _make_processor(self.page, self.document)._finalize_document()
        self.document.refresh_from_db()
        self.assertEqual(self.document.number_of_pages_processed, 1)

    def test_does_not_change_status_when_pages_remain(self):
        self.document.number_of_pages = 2
        self.document.number_of_pages_processed = 0
        self.document.save()
        _make_processor(self.page, self.document)._finalize_document()
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSING)

    def test_sets_processed_when_all_pages_done_and_no_null_embeddings(self):
        self.document.number_of_pages = 1
        self.document.number_of_pages_processed = 0
        self.document.save()
        _make_processor(self.page, self.document)._finalize_document()
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSED)

    def test_sets_incompleted_when_null_embeddings_exist(self):
        self.document.number_of_pages = 1
        self.document.number_of_pages_processed = 0
        self.document.save()
        DocumentChunk.objects.create(
            document=self.document,
            content="text",
            chunk_index=0,
            start_page=self.page,
            end_page=self.page,
            embedding=None,
        )
        _make_processor(self.page, self.document)._finalize_document()
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.INCOMPLETED)

    def test_does_not_set_final_status_when_number_of_pages_is_none(self):
        self.document.number_of_pages = None
        self.document.number_of_pages_processed = 0
        self.document.save()
        _make_processor(self.page, self.document)._finalize_document()
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSING)


class TestPageChunkProcessorProcess(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="pw"
        )
        self.document = _make_document(self.user)
        self.page = _make_page(self.document)
        self.mock_pdf = MagicMock()
        self.mock_splitter = MagicMock()
        self.mock_resolver = MagicMock()
        self.mock_resolver.resolve.return_value = ([], {})
        self.mock_embedder = MagicMock()
        result = MagicMock()
        result.embeddings = [None, None, None]
        result.has_errors.return_value = False
        self.mock_embedder.embed_batch.return_value = result

    def _processor(self):
        return PageChunkProcessor(
            page=self.page,
            document=self.document,
            pdf_extractor=self.mock_pdf,
            splitter=self.mock_splitter,
            bounding_polygon_resolver=self.mock_resolver,
            embedding_processor=self.mock_embedder,
        )

    def _setup_document(self, number_of_pages=1):
        self.document.number_of_pages = number_of_pages
        self.document.number_of_pages_processed = 0
        self.document.save()

    def test_returns_list_of_chunks(self):
        self._setup_document()
        self.mock_pdf.extract.return_value = [
            {"page_number": 1, "text": "text", "words": []}
        ]
        self.mock_splitter.split_text.return_value = ["c1", "c2"]
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "bucket"}):
            chunks = self._processor().process()
        self.assertEqual(len(chunks), 2)
        self.assertIsInstance(chunks[0], Chunk)

    def test_returns_empty_list_when_no_text(self):
        self._setup_document()
        self.mock_pdf.extract.return_value = [
            {"page_number": 1, "text": "", "words": []}
        ]
        self.mock_splitter.split_text.return_value = []
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "bucket"}):
            result = self._processor().process()
        self.assertEqual(result, [])

    def test_calls_pdf_extractor_with_bucket_and_page_key(self):
        self._setup_document()
        self.mock_pdf.extract.return_value = [
            {"page_number": 1, "text": "", "words": []}
        ]
        self.mock_splitter.split_text.return_value = []
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "my-bucket"}):
            self._processor().process()
        self.mock_pdf.extract.assert_called_once_with(
            "my-bucket", self.page.s3_key
        )

    def test_overrides_page_number_from_s3_key(self):
        self.page.s3_key = "pages/1/pages/page_5.pdf"
        self.page.save()
        self._setup_document()
        self.mock_pdf.extract.return_value = [
            {"page_number": 99, "text": "text", "words": []}
        ]
        self.mock_splitter.split_text.return_value = []
        processor = self._processor()
        captured = []
        orig = processor._text_to_chunks
        processor._text_to_chunks = lambda pages: (
            captured.extend(pages),
            orig(pages),
        )[1]
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "bucket"}):
            processor.process()
        self.assertEqual(captured[0]["page_number"], 5)

    def test_persists_chunks_to_db(self):
        self._setup_document()
        self.mock_pdf.extract.return_value = [
            {"page_number": 1, "text": "text", "words": []}
        ]
        self.mock_splitter.split_text.return_value = ["c1", "c2"]
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "bucket"}):
            self._processor().process()
        self.assertEqual(
            DocumentChunk.objects.filter(document=self.document).count(), 2
        )
