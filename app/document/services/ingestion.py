from uuid import uuid4
from django.db import transaction
from document.services.storage import upload_file_to_s3, delete_file_from_s3
from document.models import Document
from document_chunk.models import DocumentChunk
from document_chunk.services.document_chunk_processor import (
    DocumentChunkProcessor,
)
from botocore.exceptions import BotoCoreError, ClientError


def ingest_document(user, file) -> tuple[Document, list[DocumentChunk]]:
    uuid4_str = str(uuid4())
    file_extension = file.name.split(".")[-1]
    key = f"{user.email}/{uuid4_str}.{file_extension}"

    try:
        url = upload_file_to_s3(file, key=key)
    except (BotoCoreError, ClientError) as e:
        raise Exception(f"S3 upload failed: {str(e)}")

    try:
        with transaction.atomic():
            document = create_document(user=user, url=url, s3_key=key)
            document_chunks = create_document_and_chunks(document)
    except Exception:
        delete_file_from_s3(key)
        raise

    return document, document_chunks


def create_document(user, url, s3_key) -> Document:
    return Document.objects.create(user=user, url=url, s3_key=s3_key)


def create_document_and_chunks(document) -> list[DocumentChunk]:
    chunk_data = DocumentChunkProcessor(document).process()
    document_chunks = DocumentChunk.objects.bulk_create(
        [
            DocumentChunk(
                document=document,
                content=chunk["content"],
                embedding=[0.1] * 1536,
                chunk_index=chunk_idx,
            )
            for chunk_idx, chunk in enumerate(chunk_data)
        ]
    )
    return document_chunks
