from django.db import transaction
from document.models import Document
from upload_session.models import UploadSession
from document.services.storage import S3FileLoaderService


class DocumentUploadService:
    def __init__(self, user, storage: S3FileLoaderService):
        self.user = user
        self.storage = storage

    def create_upload_request(self) -> dict:
        """Creates a new document record and generates a presigned URL for
        uploading the file to S3.

        Returns:
            A dictionary containing the document ID, the presigned URL,
            the upload session ID, the document status, and the upload
            session expiration time.
        """

        with transaction.atomic():
            document = self._create_document_record()
            session = self._create_upload_session_record(document=document)
            self._assing_s3_key_to_document(document, session)

            upload_url = self.storage.generate_presigned_url_for_upload(
                upload_session_id=session.id,
                document_id=document.id,
                key=document.s3_key,
                user_id=self.user.id,
            )

        return {
            "document_id": document.id,
            "upload_session_id": session.id,
            "url": upload_url,
            "status": document.status,
            "expires_at": session.expires_at,
        }

    def _assing_s3_key_to_document(
        self, document: Document, session: UploadSession
    ):
        """Assign the S3 key to the document record based on the upload session.

        Args:
            document: The Document instance to update.
            session: The UploadSession instance containing the S3 key.
        """

        document.s3_key = self.storage.build_document_key(
            self.user.id, session.id
        )
        document.save(update_fields=["s3_key"])
        return document

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
            document=document,
            user=self.user,
            expires_at=UploadSession.default_expiration(),
        )
        return session
