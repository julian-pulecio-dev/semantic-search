import os
import logging
from typing import List

from document_chunk.models import DocumentChunk
from document_chunk.services.page_chunk_processor import (
    _extract_section_context,
)
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
from document_chunk.services.pdf_text_extractor import PDFTextExtractor
from document_chunk.services.exceptions.document_chunk_exceptions import (
    handle_persistence_errors,
)

logger = logging.getLogger(__name__)


class ChunkRefreshService:
    """
    Refreshes a chunk's content and all embeddings based on new bounding polygons.

    Pipeline:
      1. Re-extract the source PDF from S3.
      2. Match the polygon regions against the word-level coordinates on each page
         to reconstruct the text covered by the new polygons.
      3. Re-infer section_type, section_title, and context_prefix from the new text.
      4. Regenerate all three embeddings (chunk, title, doc).
      5. Persist the updated fields atomically.
    """

    _REFRESH_FIELDS = [
        "content",
        "section_type",
        "section_title",
        "context_prefix",
        "embedding",
        "embedding_title",
        "embedding_doc",
        "bounding_polygons",
        "start_page",
        "end_page",
    ]

    def __init__(
        self,
        pdf_extractor: PDFTextExtractor = None,
        embedding_processor: EmbeddingsProcessor = None,
    ):
        self.pdf_extractor = pdf_extractor or PDFTextExtractor()
        self.embedding_processor = embedding_processor or EmbeddingsProcessor()

    def refresh(
        self,
        chunk: DocumentChunk,
        bounding_polygons: list,
        start_page=None,
        end_page=None,
    ) -> DocumentChunk:
        """
        Refreshes the chunk content, context metadata, and all embeddings.

        Args:
            chunk: The DocumentChunk instance to refresh.
            bounding_polygons: List of dicts with 'page_number' and 'points' keys.
            start_page: Optional DocumentPage to update chunk.start_page.
            end_page: Optional DocumentPage to update chunk.end_page.
        Returns:
            The updated DocumentChunk instance.
        Raises:
            ValueError: If bounding_polygons is empty or no text could be extracted.
            DocumentPersistenceError: If saving fails.
        """
        if not bounding_polygons:
            raise ValueError("bounding_polygons must not be empty")

        pages = self.pdf_extractor.extract(
            os.environ["S3_BUCKET_NAME"],
            chunk.start_page.document.s3_key,
        )

        new_text = self._extract_text_from_polygons(bounding_polygons, pages)

        if not new_text.strip():
            raise ValueError(
                f"No text extracted for chunk {chunk.id} — check polygon regions"
            )

        logger.info(
            "Extracted %d chars from polygons for chunk %s",
            len(new_text),
            chunk.id,
        )

        section_type, section_title = _extract_section_context(new_text)
        context_prefix = f"[{section_type}] {section_title}"

        chunk_text = f"{context_prefix}: {new_text}"
        title_text = context_prefix
        doc_text = self._doc_context_text(chunk)

        result = self.embedding_processor.embed_batch(
            [chunk_text, title_text, doc_text]
        )
        embeddings = result.embeddings

        self._save(
            chunk,
            content=new_text,
            section_type=section_type,
            section_title=section_title,
            context_prefix=context_prefix,
            embedding=embeddings[0],
            embedding_title=embeddings[1],
            embedding_doc=embeddings[2],
            bounding_polygons=bounding_polygons,
            start_page=start_page if start_page is not None else chunk.start_page,
            end_page=end_page if end_page is not None else chunk.end_page,
        )

        return chunk

    @staticmethod
    def _doc_context_text(chunk: DocumentChunk) -> str:
        filename = (
            os.path.basename(chunk.start_page.document.s3_key or "")
            .replace("_", " ")
            .replace("-", " ")
        )
        name = os.path.splitext(filename)[0].strip()
        return f"Documento legal: {name}" if name else "Documento legal"

    def _extract_text_from_polygons(
        self, bounding_polygons: list, pages: List[dict]
    ) -> str:
        """
        Reconstructs text from pages by collecting words whose bounding boxes
        fall within the polygon regions.
        """
        pages_by_number = {p["page_number"]: p for p in pages}
        parts = []

        for polygon in bounding_polygons:
            page_number = polygon["page_number"]
            points = [tuple(pt) for pt in polygon["points"]]

            page = pages_by_number.get(page_number)
            if not page:
                continue

            x_coords = [pt[0] for pt in points]
            y_coords = [pt[1] for pt in points]
            x_min, x_max = min(x_coords), max(x_coords)
            y_min, y_max = min(y_coords), max(y_coords)

            matched = [
                w
                for w in page["words"]
                if x_min <= (w["x0"] + w["x1"]) / 2 <= x_max
                and y_min <= (w["top"] + w["bottom"]) / 2 <= y_max
            ]

            matched.sort(key=lambda w: (w["top"] // 5, w["x0"]))

            if matched:
                parts.append(" ".join(w["text"] for w in matched))

        return " ".join(parts)

    @handle_persistence_errors
    def _save(
        self,
        chunk: DocumentChunk,
        content: str,
        section_type: str,
        section_title: str,
        context_prefix: str,
        embedding: list,
        embedding_title: list,
        embedding_doc: list,
        bounding_polygons: list,
        start_page,
        end_page,
    ) -> None:
        chunk.content = content
        chunk.section_type = section_type
        chunk.section_title = section_title
        chunk.context_prefix = context_prefix
        chunk.embedding = embedding
        chunk.embedding_title = embedding_title
        chunk.embedding_doc = embedding_doc
        chunk.bounding_polygons = bounding_polygons
        chunk.start_page = start_page
        chunk.end_page = end_page
        chunk.save(update_fields=self._REFRESH_FIELDS)
        logger.info("Chunk %s refreshed and saved", chunk.id)
