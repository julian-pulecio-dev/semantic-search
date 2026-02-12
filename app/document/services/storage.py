import boto3
import os


def upload_file_to_s3(file, key: str) -> str:
    s3 = boto3.client("s3")
    s3.upload_fileobj(file, os.environ.get("S3_BUCKET_NAME"), key)

    return f"https://{os.environ.get('S3_BUCKET_NAME')}.s3.amazonaws.com/{key}"
