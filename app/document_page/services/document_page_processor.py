import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

from document.services.storage import S3FileLoaderService
from document.models import Document
from document.services.exceptions import handle_persistence_errors
from document_page.models import DocumentPage
from document_page.services.pdf_page_extractor import PDFPageExtractor

logger = logging.getLogger(__name__)


@dataclass
class DocumentPageProcessor:
    document: Document
    pdf_page_extractor: Optional[PDFPageExtractor] = field(default=None)
    s3_file_loader: Optional[S3FileLoaderService] = field(default=None)

    def _document_is_locked(self) -> bool:
        return self.document.status not in (Document.Status.PENDING, Document.Status.FAILED)

    def _lock_document(self) -> None:
        self._update_document_status(Document.Status.PROCESSING)

    def __post_init__(self):
        if self.pdf_page_extractor is None:
            self.pdf_page_extractor = PDFPageExtractor(self.document)
        if self.s3_file_loader is None:
            self.s3_file_loader = S3FileLoaderService(
                os.environ["S3_BUCKET_NAME"]
            )

    @handle_persistence_errors
    def _update_document_status(self, status: str) -> None:
        self.document.status = status
        self.document.save(update_fields=["status"])
        logger.info(
            "Updated document %s status to %s",
            self.document.id,
            status,
        )

    def _upload_page(self, s3_key: str, pdf_bytes: bytes) -> None:
        logger.info("Uploading page to S3 with key %s", s3_key)
        self.s3_file_loader.upload_file(
            key=s3_key,
            body=pdf_bytes,
            content_type="application/pdf",
        )

    @handle_persistence_errors
    def _persist_page(self, s3_key: str) -> DocumentPage:
        return DocumentPage.objects.create(
            document=self.document,
            s3_key=s3_key, 
        )

    def process(self) -> List[DocumentPage]:
        logger.info("Processing document %s", self.document.id)

        if self._document_is_locked():
            logger.warning(
                "Document %s is already being processed by another worker",
                self.document.id,
            )
            return []
        self._lock_document()

        document_stream = self.s3_file_loader.get_file(self.document.s3_key)
        pages: List[DocumentPage] = []

        for page_data in self.pdf_page_extractor.split_to_bytes_stream(
            document_stream
        ):
            s3_key = self.s3_file_loader.build_page_key(
                self.document.id, page_data.page_number
            )
            self._upload_page(s3_key, page_data.pdf_bytes)

            page = self._persist_page(s3_key)
            pages.append(page)

            logger.info(
                "Processed page %s of document %s",
                page_data.page_number,
                self.document.id,
            )

        return pages
