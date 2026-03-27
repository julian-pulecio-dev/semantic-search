import os
import logging
import boto3
import pdfplumber

from dataclasses import dataclass, field
from typing import Optional, List
from io import BytesIO

from document.models import Document
from document_chunk.models import DocumentChunk
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class DocumentProcessingError(Exception):
    """Raised when a document cannot be fetched or parsed."""


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


@dataclass(frozen=True)
class Chunk:
    """
    Immutable domain object. An embedding-enriched version is produced
    via Chunk.with_embedding() rather than mutating the instance.
    """

    content: str
    page_number: int
    document_id: int
    embedding: Optional[list] = field(default=None, hash=False, compare=False)

    def with_embedding(self, embedding: list) -> "Chunk":
        """
        Return a new Chunk with the embedding attached.
        Args:
            embedding: The embedding to attach to the chunk.
        Returns:
            A new Chunk instance with the embedding attached.
        """
        return Chunk(
            content=self.content,
            page_number=self.page_number,
            document_id=self.document_id,
            embedding=embedding,
        )


class DocumentChunkProcessor:
    """
    Processor responsible for chunking a document and generating embeddings.
    """

    LINE_TOLERANCE = 3

    def __init__(
        self,
        document: Document,
        *,
        s3_client=None,
        embedding_processor: Optional[EmbeddingsProcessor] = None,
        splitter: Optional[RecursiveCharacterTextSplitter] = None,
        line_tolerance: int = LINE_TOLERANCE,
    ):
        self.document = document
        self.line_tolerance = line_tolerance

        self.s3_client = s3_client or boto3.client("s3")
        self.embedding_processor = embedding_processor or EmbeddingsProcessor()
        self.splitter = (
            splitter
            or RecursiveCharacterTextSplitter.from_tiktoken_encoder(
                encoding_name="cl100k_base",
                chunk_size=500,
                chunk_overlap=50,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
        )

    def process(self) -> List[Chunk]:
        """
        Process the document by fetching it from S3, converting it to text,
        chunking the text, and generating embeddings for each chunk.
        Returns:
            A list of Chunk instances with embeddings attached.
        Raises:
            DocumentProcessingError: If fetching or parsing the document fails.
        """
        logger.info("Processing document %s", self.document.id)

        file_stream = self._get_s3_file(
            os.environ["S3_BUCKET_NAME"],
            self.document.s3_key,
        )

        pages = self._pdf_to_text(file_stream)
        chunks = self._text_to_chunks(pages)

        logger.info(
            "Generated %d chunks for document %s",
            len(chunks),
            self.document.id,
        )

        chunks = self._attach_embeddings(chunks)

        logger.info(
            "Embedding generation completed for document %s", self.document.id
        )

        self._save_chunks(chunks)

        return chunks

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

            logger.debug(
                "Extracted %d pages from document %s",
                len(pages_output),
                self.document.id,
            )
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
            The extracted text from the page, with special handling
            for two-column layouts.
        Raises:
            DocumentProcessingError: If text extraction fails.
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
        two-column only if fewer than 5% of words fall in the center band,
        which avoids false positives from indented blocks or sidebars.
        Args:
            page: A pdfplumber page object.
            words: A list of word dicts extracted from the page.
        Returns:
            True if the page likely has a two-column layout, False otherwise.
        Raises:
            DocumentProcessingError: If layout detection fails.
        """
        page_width = page.width
        mid_x = page_width / 2
        gap_half_width = page_width * 0.08

        gap_left = mid_x - gap_half_width
        gap_right = mid_x + gap_half_width

        words_in_gap = [w for w in words if gap_left <= w["x0"] <= gap_right]
        left_words = [w for w in words if w["x0"] < gap_left]
        right_words = [w for w in words if w["x0"] > gap_right]

        if not left_words or not right_words:
            return False

        gap_density = len(words_in_gap) / len(words)
        return gap_density < 0.05

    def _extract_two_columns(self, page, words) -> str:
        """
        Extracts text from a two-column page by splitting words
        into left and right groups, grouping them into lines,
        and concatenating the lines in the correct order.
        Args:
            page: A pdfplumber page object.
            words: A list of word dicts extracted from the page.
        Returns:
            The extracted text from the page, with columns correctly
            ordered.
        Raises:
            DocumentProcessingError: If text extraction fails.
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
        Args:
            words: A list of word dicts extracted from the page.
        Returns:
            A dictionary mapping line tops to lists of words in that line.
        Raises:
            DocumentProcessingError: If line grouping fails.
        """
        lines = {}

        for word in words:
            placed = False
            for top in list(lines.keys()):
                if abs(word["top"] - top) <= self.line_tolerance:
                    lines[top].append(word)
                    placed = True
                    break

            if not placed:
                lines[word["top"]] = [word]

        for top in lines:
            lines[top].sort(key=lambda w: w["x0"])

        return lines

    def _lines_to_text(self, lines: dict) -> List[str]:
        """
        Converts a dictionary of lines into a list of text strings.
        Args:
            lines: A dictionary mapping line tops to lists of words in that line.
        Returns:
            A list of strings, each representing a line of text.
        Raises:
            DocumentProcessingError: If text conversion fails.
        """
        return [
            " ".join(w["text"] for w in lines[top])
            for top in sorted(lines.keys())
        ]

    def _text_to_chunks(self, pages_data: List[dict]) -> List[Chunk]:
        """
        Converts page text into chunks using the configured text splitter.
        Args:
            pages_data: A list of dictionaries containing page text and metadata.
        Returns:
            A list of Chunk objects representing the text chunks.
        Raises:
            DocumentProcessingError: If chunking fails.
        """
        chunks: List[Chunk] = []

        for page in pages_data:
            for text in self.splitter.split_text(page["text"]):
                chunks.append(
                    Chunk(
                        content=text,
                        page_number=page["page_number"],
                        document_id=self.document.id,
                    )
                )

        return chunks

    def _attach_embeddings(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        Attaches embeddings to chunks via a single batch API call when
        embed_batch() is available on the processor, falling back to
        sequential calls otherwise. Batch is strongly preferred at scale.
        Args:
            chunks: A list of Chunk objects to attach embeddings to.
        Returns:
            A list of Chunk objects with embeddings attached.
        Raises:
            EmbeddingError: If embedding generation fails.
        """
        try:
            texts = [c.content for c in chunks]

            if hasattr(self.embedding_processor, "embed_batch"):
                result = self.embedding_processor.embed_batch(texts)
                result.raise_on_errors()

                if len(result.embeddings) != len(chunks):
                    raise EmbeddingError(
                        f"Embedding count mismatch: got {len(result.embeddings)}, "
                        f"expected {len(chunks)}"
                    )

                embeddings = result.embeddings
            else:
                logger.warning(
                    "embed_batch() not available on EmbeddingsProcessor — "
                    "falling back to sequential calls. Consider implementing "
                    "embed_batch() for better performance."
                )
                embeddings = [
                    self.embedding_processor.chunk_text_to_embeddings(t)
                    for t in texts
                ]

            return [
                chunk.with_embedding(emb)
                for chunk, emb in zip(chunks, embeddings)
            ]

        except EmbeddingError:
            raise
        except Exception as e:
            raise EmbeddingError(
                f"Failed generating embeddings for document {self.document.id}: {e}"
            ) from e

    def _save_chunks(self, chunks: List[Chunk]) -> None:
        """
        Persists chunks to the database, replacing any existing chunks
        for this document.
        Args:
            chunks: A list of Chunk objects with embeddings attached.
        Raises:
            DocumentProcessingError: If saving fails.
        """
        try:
            DocumentChunk.objects.bulk_create(
                [
                    DocumentChunk(
                        document=self.document,
                        content=chunk.content,
                        embedding=chunk.embedding,
                        chunk_index=index,
                    )
                    for index, chunk in enumerate(chunks)
                ]
            )

            logger.info(
                "Saved %d chunks for document %s",
                len(chunks),
                self.document.id,
            )
        except Exception as e:
            raise DocumentProcessingError(
                f"Failed saving chunks for document {self.document.id}: {e}"
            ) from e
