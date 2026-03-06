from rest_framework import serializers


class UploadSessionSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(read_only=True)
    url = serializers.JSONField()
    status = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
