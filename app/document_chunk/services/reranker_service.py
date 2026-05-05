import logging
from typing import List

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from document_chunk.models import DocumentChunk
from document_chunk.services.exceptions.reranker_exceptions import RerankerError

logger = logging.getLogger(__name__)

_MODEL_ARN = "arn:aws:bedrock:{region}::foundation-model/cohere.rerank-v3-5:0"


class RerankerService:
    """
    Two-stage retrieval reranker using Amazon Bedrock's reranking model.

    Intended usage:
      1. Retrieve a larger candidate pool from pgvector (e.g. k * 3).
      2. Call rerank(query, candidates, top_n=k) to get the final ranked list.

    The Bedrock reranking model scores each (query, chunk) pair as a unit,
    producing relevance scores that are more accurate than cosine distance alone.
    """

    def __init__(
        self,
        region: str = "us-east-1",
        read_timeout: int = 60,
        connect_timeout: int = 10,
    ):
        self._model_arn = _MODEL_ARN.format(region=region)
        config = Config(
            read_timeout=read_timeout,
            connect_timeout=connect_timeout,
        )
        self._client = boto3.client(
            "bedrock-agent-runtime",
            region_name=region,
            config=config,
        )

    def rerank(
        self,
        query: str,
        chunks: List[DocumentChunk],
        top_n: int,
    ) -> List[DocumentChunk]:
        """
        Reranks chunks by relevance to query.

        Attaches `rerank_score` (float, higher = more relevant) to each
        returned chunk. Returns at most `top_n` chunks in descending order.
        """
        if not chunks:
            return []

        top_n = min(top_n, len(chunks))

        try:
            response = self._client.rerank(
                queries=[
                    {
                        "type": "TEXT",
                        "textQuery": {"text": query},
                    }
                ],
                sources=[
                    {
                        "type": "INLINE",
                        "inlineDocumentSource": {
                            "type": "TEXT",
                            "textDocument": {"text": chunk.content},
                        },
                    }
                    for chunk in chunks
                ],
                rerankingConfiguration={
                    "type": "BEDROCK_RERANKING_MODEL",
                    "bedrockRerankingConfiguration": {
                        "numberOfResults": top_n,
                        "modelConfiguration": {
                            "modelArn": self._model_arn,
                        },
                    },
                },
            )
        except ClientError as exc:
            logger.error("Bedrock reranking failed: %s", exc)
            raise RerankerError(f"Reranking API call failed: {exc}") from exc

        logger.debug("Bedrock rerank raw response keys: %s", list(response.keys()))
        logger.debug("Bedrock rerank raw response: %s", response)

        results = (
            response.get("rerankingResults")
            or response.get("results")
            or response.get("textResults")
            or []
        )

        reranked: List[DocumentChunk] = []
        for result in results:
            idx = result.get("index")
            score = result.get("relevanceScore") or result.get("score")
            if idx is None or score is None:
                logger.warning("Unexpected rerank result format: %s", result)
                continue
            chunk = chunks[idx]
            chunk.rerank_score = score
            reranked.append(chunk)

        if not reranked:
            logger.warning(
                "Reranker returned no results. Response keys: %s. "
                "Falling back to pgvector order.",
                list(response.keys()),
            )
            return chunks[:top_n]

        return reranked
