import logging
import boto3
import pdfplumber

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List
from io import BytesIO

from document_chunk.services.exceptions import DocumentProcessingError

logger = logging.getLogger(__name__)


@dataclass
class PDFTextExtractor:
    """
    Responsible for fetching a PDF from S3 and converting it to a list
    of page dicts with extracted text.

    Handles single-column and two-column layouts transparently. All PDF
    parsing logic is isolated here so it can be tested independently of
    the chunking and embedding pipeline.
    """

    LINE_TOLERANCE: int = 3
    TWO_COLUMN_GAP_THRESHOLD: float = 0.05

    s3_client: object = field(default=None)
    line_tolerance: int = field(default=LINE_TOLERANCE)
    two_column_gap_threshold: float = field(default=TWO_COLUMN_GAP_THRESHOLD)

    def __post_init__(self):
        if self.s3_client is None:
            self.s3_client = boto3.client("s3")

    def extract(self, bucket: str, key: str) -> List[dict]:
        """
        Fetches the PDF at s3://bucket/key and returns a list of page dicts.
        Args:
            bucket: The S3 bucket name.
            key: The S3 key for the document.
        Returns:
            A list of dicts, each containing 'page_number' and 'text' keys,
            in page order. Pages with no extractable text are omitted.
        Raises:
            DocumentProcessingError: If the file cannot be fetched or parsed.
        """
        file_stream = self._get_s3_file(bucket, key)
        return self._pdf_to_text(file_stream)

    def _get_s3_file(self, bucket: str, key: str) -> BytesIO:
        """
        Fetches the file from S3 and returns a BytesIO stream.
        Args:
            bucket: The S3 bucket name.
            key: The S3 key for the document.
        Returns:
            A BytesIO stream of the file content.
        Raises:
            DocumentProcessingError: If the file cannot be fetched from S3.
        """
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return BytesIO(response["Body"].read())
        except Exception as e:
            raise DocumentProcessingError(
                f"Could not fetch s3://{bucket}/{key}: {e}"
            ) from e

    def _pdf_to_text(self, file_stream: BytesIO) -> List[dict]:
        """
        Converts a PDF file stream to a list of page dicts with page number and text.
        Args:
            file_stream: A BytesIO stream of the PDF file.
        Returns:
            A list of dicts, each containing 'page_number' and 'text' keys.
        Raises:
            DocumentProcessingError: If the PDF cannot be parsed.
        """
        try:
            pages_output = []

            with pdfplumber.open(file_stream) as pdf:
                for page_number, page in enumerate(pdf.pages, start=1):
                    text = self._extract_page_text(page)

                    if text:
                        pages_output.append(
                            {
                                "page_number": page_number,
                                "text": text.strip(),
                            }
                        )

            logger.debug("Extracted %d pages from PDF", len(pages_output))
            return pages_output

        except DocumentProcessingError:
            raise
        except Exception as e:
            raise DocumentProcessingError(f"Failed to parse PDF: {e}") from e

    def _extract_page_text(self, page) -> str:
        """
        Extracts text from a PDF page, with special handling for two-column layouts.
        Args:
            page: A pdfplumber page object.
        Returns:
            The extracted text from the page.
        """
        simple_text = page.extract_text()
        if not simple_text:
            return ""

        words = page.extract_words()

        if words and self._is_two_column_layout(page, words):
            return self._extract_two_columns(page, words)

        return simple_text

    def _is_two_column_layout(self, page, words) -> bool:
        """
        Detects a two-column layout by checking for a low-density gap
        around the horizontal midpoint of the page. A page is considered
        two-column only if fewer than `two_column_gap_threshold` (default 5%)
        of words fall in the center band, which avoids false positives from
        indented blocks or sidebars.

        All x-coordinates are normalised to [0, 1] relative to page width
        before comparison, so detection is consistent regardless of the
        physical dimensions of the PDF.
        Args:
            page: A pdfplumber page object.
            words: A list of word dicts extracted from the page.
        Returns:
            True if the page likely has a two-column layout, False otherwise.
        """
        page_width = page.width

        # Normalise x0 to [0, 1] so thresholds are dimension-independent.
        relative_x0 = [w["x0"] / page_width for w in words]

        gap_left = 0.5 - 0.08
        gap_right = 0.5 + 0.08

        words_in_gap = sum(
            1 for x in relative_x0 if gap_left <= x <= gap_right
        )
        left_count = sum(1 for x in relative_x0 if x < gap_left)
        right_count = sum(1 for x in relative_x0 if x > gap_right)

        if not left_count or not right_count:
            return False

        gap_density = words_in_gap / len(words)
        return gap_density < self.two_column_gap_threshold

    def _extract_two_columns(self, page, words) -> str:
        """
        Extracts text from a two-column page by splitting words into left
        and right groups, grouping them into lines, and concatenating the
        lines in reading order (left column first, then right).
        Args:
            page: A pdfplumber page object.
            words: A list of word dicts extracted from the page.
        Returns:
            The extracted text from the page with columns correctly ordered.
        """
        mid_x = page.width / 2

        left = [w for w in words if w["x0"] < mid_x]
        right = [w for w in words if w["x0"] >= mid_x]

        lines = self._lines_to_text(
            self._group_words_into_lines(left)
        ) + self._lines_to_text(self._group_words_into_lines(right))

        return "\n".join(lines)

    def _group_words_into_lines(self, words) -> dict:
        """
        Groups words into lines based on their vertical positions.

        Each word's `top` coordinate is quantised to the nearest multiple of
        `line_tolerance`, so all words on the same visual line map to the same
        bucket key. This makes grouping O(n) instead of O(n²).
        Args:
            words: A list of word dicts extracted from the page.
        Returns:
            A dictionary mapping quantised line tops to lists of words in that
            line, with words sorted left-to-right by x0.
        """
        lines: defaultdict[int, list] = defaultdict(list)

        for word in words:
            bucket = (
                round(word["top"] / self.line_tolerance) * self.line_tolerance
            )
            lines[bucket].append(word)

        for bucket in lines:
            lines[bucket].sort(key=lambda w: w["x0"])

        return dict(lines)

    def _lines_to_text(self, lines: dict) -> List[str]:
        """
        Converts a dictionary of lines into a list of text strings.
        Args:
            lines: A dictionary mapping line tops to lists of words in that line.
        Returns:
            A list of strings, each representing a line of text.
        """
        return [
            " ".join(w["text"] for w in lines[top])
            for top in sorted(lines.keys())
        ]
