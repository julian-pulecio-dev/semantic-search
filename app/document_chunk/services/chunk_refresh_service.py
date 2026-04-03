import os
import logging
from typing import List

from document_chunk.models import DocumentChunk
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
from document_chunk.services.pdf_text_extractor import PDFTextExtractor
from document_chunk.services.exceptions.document_chunk_exceptions import (
    handle_persistence_errors,
)

logger = logging.getLogger(__name__)


class ChunkRefreshService:
    """
    Refreshes a chunk's content and embedding based on new bounding polygons.

    Pipeline:
      1. Re-extract the source PDF from S3.
      2. Match the polygon regions against the word-level coordinates on each page
         to reconstruct the text covered by the new polygons.
      3. Regenerate the embedding for the new text.
      4. Persist the updated content, embedding, and bounding_polygons.
    """

    _REFRESH_FIELDS = ["content", "embedding", "bounding_polygons"]

    def __init__(
        self,
        pdf_extractor: PDFTextExtractor = None,
        embedding_processor: EmbeddingsProcessor = None,
    ):
        self.pdf_extractor = pdf_extractor or PDFTextExtractor()
        self.embedding_processor = embedding_processor or EmbeddingsProcessor()

    def refresh(
        self, chunk: DocumentChunk, bounding_polygons: list
    ) -> DocumentChunk:
        """
        Refreshes the chunk content and embedding from the given bounding polygons.

        Args:
            chunk: The DocumentChunk instance to refresh.
            bounding_polygons: List of dicts with 'page_number' and 'points' keys.
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
            chunk.document.s3_key,
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

        embedding = self.embedding_processor.get_embedding(new_text)

        self._save(chunk, new_text, embedding, bounding_polygons)

        return chunk

    def _extract_text_from_polygons(
        self, bounding_polygons: list, pages: List[dict]
    ) -> str:
        """
        Reconstructs text from pages by collecting words whose bounding boxes
        fall within the polygon regions.

        For each polygon entry (page_number + points), words on the matching page
        whose centres lie inside the polygon bounding box are collected in reading
        order and joined into a single string.

        Args:
            bounding_polygons: List of dicts with 'page_number' and 'points'.
            pages: Page dicts from PDFTextExtractor, each with 'page_number'
            and 'words'.
        Returns:
            Reconstructed text string.
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

            # Group words into lines using a tolerance band instead of rounding,
            # to avoid mis-sorting words on lines that straddle integer boundaries.
            matched.sort(key=lambda w: (w["top"] // 5, w["x0"]))

            if matched:
                parts.append(" ".join(w["text"] for w in matched))

        return " ".join(parts)

    @handle_persistence_errors
    def _save(
        self,
        chunk: DocumentChunk,
        content: str,
        embedding: list,
        bounding_polygons: list,
    ) -> None:
        chunk.content = content
        chunk.embedding = embedding
        chunk.bounding_polygons = bounding_polygons
        chunk.save(update_fields=self._REFRESH_FIELDS)
        logger.info("Chunk %s refreshed and saved", chunk.id)
