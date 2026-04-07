from rest_framework import serializers
from upload_session.models import UploadSession
from document.models import Document


class CreateUploadSessionSerializer(serializers.Serializer):
    document_type = serializers.CharField(max_length=100)


class PresignedPostFieldsSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="S3 object key")
    Content_Type = serializers.CharField(source="Content-Type")
    x_amz_server_side_encryption = serializers.CharField(source="x-amz-server-side-encryption")
    x_amz_meta_upload_session_id = serializers.UUIDField(source="x-amz-meta-upload-session-id")
    x_amz_meta_document_id = serializers.UUIDField(source="x-amz-meta-document-id")
    x_amz_meta_user_id = serializers.UUIDField(source="x-amz-meta-user-id")
    policy = serializers.CharField()

    def to_representation(self, instance):
        # Pass through all fields from boto3 without filtering,
        # since auth fields vary between IAM users (v2) and STS roles (v4).
        return instance


class PresignedPostUrlSerializer(serializers.Serializer):
    url = serializers.URLField(help_text="S3 presigned POST endpoint")
    fields = PresignedPostFieldsSerializer()
    upload_session_id = serializers.UUIDField()
    document_id = serializers.UUIDField()


class UploadSessionSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(
        source="upload_session_id", read_only=True
    )
    document_id = serializers.UUIDField(read_only=True)
    url = PresignedPostUrlSerializer()
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
