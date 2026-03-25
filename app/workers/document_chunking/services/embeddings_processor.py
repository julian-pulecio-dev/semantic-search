import boto3
import json
import time
from botocore.exceptions import ClientError


class EmbeddingsProcessor:
    def __init__(self, document):
        self.document = document
        self.model_id = "amazon.titan-embed-text-v2:0"

        self.bedrock_client = boto3.client(
            service_name="bedrock-runtime", region_name="us-east-1"
        )

    def chunk_text_to_embeddings(self, chunk_text: str) -> list[float]:
        max_retries = 3
        backoff = 1

        for attempt in range(max_retries):
            try:
                response = self.bedrock_client.invoke_model(
                    modelId=self.model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps({"inputText": chunk_text}),
                )

                result = json.loads(response["body"].read())

                embedding = result.get("embedding")

                if not embedding:
                    raise ValueError("No embedding returned from model")

                return embedding

            except ClientError as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(backoff)
                backoff *= 2
