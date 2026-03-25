import boto3
import os
import pdfplumber
from io import BytesIO
from document.models import Document
from document_chunk.services.embeddings_processor import EmbeddingsProcessor
from langchain_text_splitters import RecursiveCharacterTextSplitter


class Chunk:
    def __init__(self, content: str, page_number: int, document_id: int):
        self.content = content
        self.page_number = page_number
        self.document_id = document_id
        self.embedding = None


class DocumentChunkProcessor:
    LINE_TOLERANCE = 3

    def __init__(self, document: Document):
        self.document = document
        self.s3_client = boto3.client("s3")
        self.embedding_processor = EmbeddingsProcessor(document)

    def process(self):
        file_stream = self._get_s3_file(
            os.environ["S3_BUCKET_NAME"], self.document.s3_key
        )
        pages_text = self._pdf_to_text(file_stream)
        chunks = self._text_to_chunks(pages_text)
        for chunk in chunks:
            chunk.embedding = (
                self.embedding_processor.chunk_text_to_embeddings(
                    chunk.content
                )
            )
        return chunks

    def _get_s3_file(self, bucket_name: str, file_key: str) -> BytesIO:
        response = self.s3_client.get_object(Bucket=bucket_name, Key=file_key)
        return BytesIO(response["Body"].read())

    def _pdf_to_text(self, file_stream: BytesIO):
        pages_output = []

        with pdfplumber.open(file_stream) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                page_text = self._extract_page_text(page)
                if page_text:
                    pages_output.append(
                        {
                            "page_number": page_number,
                            "text": page_text.strip(),
                        }
                    )

        return pages_output

    def _extract_page_text(self, page) -> str:
        simple_text = page.extract_text()

        if not simple_text:
            return ""

        words = page.extract_words()

        if words and self._is_two_column_layout(page, words):
            return self._extract_two_columns(page, words)

        return simple_text

    def _is_two_column_layout(self, page, words) -> bool:
        page_width = page.width
        mid_x = page_width / 2

        left = [w for w in words if w["x0"] < mid_x]
        right = [w for w in words if w["x0"] >= mid_x]

        if not left or not right:
            return False

        left_avg_x = sum(w["x0"] for w in left) / len(left)
        right_avg_x = sum(w["x0"] for w in right) / len(right)

        return abs(right_avg_x - left_avg_x) > page_width * 0.3

    def _extract_two_columns(self, page, words) -> str:
        page_width = page.width
        mid_x = page_width / 2

        left_column = []
        right_column = []

        for word in words:
            if word["x0"] < mid_x:
                left_column.append(word)
            else:
                right_column.append(word)

        left_lines = self._group_words_into_lines(left_column)
        right_lines = self._group_words_into_lines(right_column)

        merged_lines = []

        for top in sorted(left_lines.keys()):
            merged_lines.append(self._line_to_text(left_lines[top]))

        for top in sorted(right_lines.keys()):
            merged_lines.append(self._line_to_text(right_lines[top]))

        return "\n".join(merged_lines)

    def _group_words_into_lines(self, words):
        lines = {}

        for word in words:
            placed = False

            for existing_top in list(lines.keys()):
                if abs(word["top"] - existing_top) <= self.LINE_TOLERANCE:
                    lines[existing_top].append(word)
                    placed = True
                    break

            if not placed:
                lines[word["top"]] = [word]

        for top in lines:
            lines[top].sort(key=lambda w: w["x0"])

        return lines

    def _line_to_text(self, words):
        return " ".join(w["text"] for w in words)

    def _text_to_chunks(self, pages_data: list) -> list:
        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        chunks = []

        for page in pages_data:
            page_chunks = splitter.split_text(page["text"])

            for chunk in page_chunks:
                chunk_obj = Chunk(
                    content=chunk,
                    page_number=page["page_number"],
                    document_id=self.document.id,
                )
                chunks.append(chunk_obj)

        return chunks
