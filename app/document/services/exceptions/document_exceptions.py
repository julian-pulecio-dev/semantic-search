from django.db import DatabaseError

from core.exceptions.base_exception_handler import BaseErrorHandler
from document.models import Document



class DocumentProcessingError(Exception):

    def __init__(self, message: str, document: Document = None):
        super().__init__(message)
        if document is not None and document.status != Document.Status.FAILED:
            document.status = Document.Status.FAILED
            document.save(update_fields=["status"])
    """
    Base domain exception for the document chunk processing pipeline.
    Catch this to handle any processing failure regardless of cause.
    """

    pass


class DocumentPersistenceError(DocumentProcessingError):
    """
    Raised when a database operation fails during processing.
    Typically transient — safe to retry after a delay.
    """

    pass


class DocumentInvalidStatusError(DocumentProcessingError):
    """
    Raised when the document is not in the expected status for processing.
    Indicates an orchestration or programming mistake — should not be retried.
    """

    pass


class PersistenceErrorHandler(BaseErrorHandler):
    catches = (DatabaseError,)

    def handle(self, exc: Exception) -> DocumentPersistenceError:
        return DocumentPersistenceError(f"Database operation failed: {exc}")


handle_persistence_errors = PersistenceErrorHandler()
