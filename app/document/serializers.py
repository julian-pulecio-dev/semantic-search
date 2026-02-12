from rest_framework import serializers
from .services.storage import upload_file_to_s3
from core.models import Document


class DocumentSerializer(serializers.ModelSerializer):
    """Serializer for Document model"""

    file = serializers.FileField(write_only=True)

    class Meta:
        model = Document
        fields = ("file", "url", "uploaded_at")
        read_only_fields = ("url", "uploaded_at")

    def create(self, validated_data):
        file = validated_data.pop("file")
        user = self.context["request"].user

        url = upload_file_to_s3(file, user.email + "/" + file.name)

        return Document.objects.create(user=user, url=url, **validated_data)
