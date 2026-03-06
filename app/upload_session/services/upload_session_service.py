from django.db import transaction

from document.services.storage import S3FileLoaderService
from document.models import Document
from upload_session.models import UploadSession


class UploadSessionService:

    def __init__(self, user, storage: S3FileLoaderService):
        self.user = user
        self.storage = storage

    def create_upload_session(self) -> dict:
        """Creates a new document record, an associated upload session, and
        generates a presigned URL for uploading the file to S3.

        Returns:
            A dictionary containing the document ID, the upload session ID,
            the presigned URL, and the upload session expiration time.
        """

        with transaction.atomic():
            document = self._create_document_record()
            session = self._create_upload_session_record(document=document)

        url = self.storage.generate_presigned_url_for_upload(
            document.s3_key, user_id=self.user.id
        )

        return {
            "document_id": document.id,
            "upload_session_id": session.id,
            "url": url,
            "expires_at": session.expires_at,
        }

    def _create_document_record(self) -> Document:
        """Create a new document record in the database with a status of
        PENDING.

        Returns:
            The created Document instance.
        """

        document = Document.objects.create(
            user=self.user,
            status=Document.Status.PENDING,
        )
        document.s3_key = self.storage.build_document_key(
            self.user.id, document.id
        )
        document.save(update_fields=["s3_key"])
        return document

    def _create_upload_session_record(
        self, document: Document
    ) -> UploadSession:
        """Create a new upload session record in the database.

        Args:
            document: The Document instance associated with the upload session.
        Returns:
            The created UploadSession instance.
        """
        session = UploadSession.objects.create(
            user=self.user,
            document=document,
            expires_at=UploadSession.default_expiration(),
            s3_key=document.s3_key,
        )
        return session
