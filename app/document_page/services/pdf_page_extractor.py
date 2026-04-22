import logging
from dataclasses import dataclass
from typing import Generator
import pymupdf
from botocore.response import StreamingBody

from document.services.exceptions import DocumentProcessingError
from document.models import Document

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageData:
    page_number: int
    pdf_bytes: bytes


MAX_PAGES = 5000
MAX_SIZE_BYTES = 200 * 1024 * 1024

@dataclass
class PDFPageExtractor:
    document: Document

    def _read_with_limit(self, body: StreamingBody) -> bytes:
        chunks = []
        total = 0

        for chunk in body.iter_chunks(chunk_size=1024 * 1024):
            total += len(chunk)
            if total > MAX_SIZE_BYTES:
                raise DocumentProcessingError(
                    f"PDF too large (limit: {MAX_SIZE_BYTES / 1024 / 1024:.0f} MB)",
                    self.document
                )
            chunks.append(chunk)

        return b"".join(chunks)

    def _split_document(
        self, doc: pymupdf.Document
    ) -> Generator[PageData, None, None]:
        page_count = len(doc)

        if page_count == 0:
            raise DocumentProcessingError("PDF has no pages", self.document)

        if page_count > MAX_PAGES:
            raise DocumentProcessingError(
                f"Too many pages: {page_count} (limit: {MAX_PAGES})", self.document
            )

        for i in range(page_count):
            page_doc = pymupdf.open()

            try:
                page_doc.insert_pdf(doc, from_page=i, to_page=i)

                yield PageData(page_number=i + 1, pdf_bytes=page_doc.tobytes())

            finally:
                page_doc.close()

    def split_to_bytes_stream(
        self, body: StreamingBody
    ) -> Generator[PageData, None, None]:

        try:
            doc = None
            try:
                pdf_bytes = self._read_with_limit(body)
                doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
                del pdf_bytes

                if doc.is_encrypted:
                    raise DocumentProcessingError(
                        "PDF is encrypted and cannot be processed",
                        self.document
                    )

                yield from self._split_document(doc)

            finally:
                if doc is not None:
                    doc.close()

        except DocumentProcessingError:
            raise

        except Exception as e:
            logger.exception("Failed to split PDF")
            raise DocumentProcessingError(f"Failed to split PDF: {e}", self.document) from e
