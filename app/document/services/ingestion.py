import os
from document.services.storage import S3FileLoader
from document.models import Document, DocumentStatus

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")


def create_document_request(user) -> dict:
    document = create_document(user=user, s3_key="temp")

    key = f"{document.user.email}/{document.id}"
    document.s3_key = key
    document.save(update_fields=["s3_key"])

    pre_signed_url = create_pre_signed_url_for_document(document, key)

    return {
        "document_id": document.id,
        "url": pre_signed_url,
        "status": document.status,
    }


def create_document(user, s3_key) -> Document:
    document = Document.objects.create(
        user=user,
        status=DocumentStatus.PENDING,
    )
    document.s3_key = s3_key
    document.save()
    return document

def create_pre_signed_url_for_document(document, key) -> str:
    s3_loader = S3FileLoader(bucket_name=BUCKET_NAME)
    pre_signed_url = s3_loader.generate_presigned_url_for_upload(
        key=key, user_email=str(document.user.email)
    )
    return pre_signed_url
