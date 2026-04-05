from rest_framework import serializers
from upload_session.models import UploadSession
from document.models import Document
from drf_spectacular.utils import extend_schema_field, inline_serializer


class CreateUploadSessionSerializer(serializers.Serializer):
    document_type = serializers.CharField(max_length=100)


class UploadSessionSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(
        source="upload_session_id", read_only=True
    )
    document_id = serializers.UUIDField(read_only=True)
    url = extend_schema_field(
        inline_serializer(
            name="PresignedPostUrl",
            fields={
                "url": serializers.URLField(help_text="S3 presigned POST endpoint"),
                "fields": inline_serializer(
                    name="PresignedPostFields",
                    fields={
                        "key": serializers.CharField(help_text="S3 object key"),
                        "Content-Type": serializers.CharField(),
                        "acl": serializers.CharField(),
                        "x-amz-server-side-encryption": serializers.CharField(),
                        "x-amz-meta-upload-session-id": serializers.UUIDField(),
                        "x-amz-meta-document-id": serializers.UUIDField(),
                        "x-amz-meta-user-id": serializers.UUIDField(),
                        "AWSAccessKeyId": serializers.CharField(),
                        "policy": serializers.CharField(),
                        "signature": serializers.CharField(),
                    },
                ),
                "upload_session_id": serializers.UUIDField(),
                "document_id": serializers.UUIDField(),
            },
        )
    )(serializers.JSONField())
    status = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "status", "s3_key", "uploaded_at"]
        read_only_fields = fields


class UploadSessionDetailSerializer(serializers.ModelSerializer):
    document = DocumentSerializer(read_only=True)

    class Meta:
        model = UploadSession
        fields = ["id", "status", "expires_at", "created_at", "document"]
        read_only_fields = fields
