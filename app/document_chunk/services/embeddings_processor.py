import boto3
import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Generator

from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

RETRYABLE_ERROR_CODES = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "ModelTimeoutException",
}


@dataclass
class BatchEmbeddingResult:
    """
    Represents the result of a batch embedding operation.
    """

    embeddings: List[Optional[List[float]]] = field(default_factory=list)
    errors: Dict[int, Exception] = field(default_factory=dict)
    throttle_count: int = 0

    @property
    def success_count(self) -> int:
        """Returns the number of successfully generated embeddings."""
        return sum(1 for e in self.embeddings if e is not None)

    @property
    def failed_indices(self) -> List[int]:
        """Returns the indices of embeddings that failed."""
        return list(self.errors.keys())

    def has_errors(self) -> bool:
        """Returns True if any embeddings failed, False otherwise."""
        return bool(self.errors)

    def raise_on_errors(self) -> None:
        """Raises a RuntimeError if any embeddings failed."""
        if self.errors:
            idx, exc = next(iter(self.errors.items()))
            raise RuntimeError(
                f"{len(self.errors)} embedding(s) failed. "
                f"First failure at index {idx}."
            ) from exc


class TitanEmbeddingAdapter:
    """
    Titan request/response adapter.
    Yields payloads one at a time to avoid duplicating
    the full input list in memory.
    """

    def build_requests(
        self, texts: List[str]
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Builds request payloads for a list of input texts.
        Args:
            texts: A list of input strings to be embedded.
        Yields:
            A dictionary representing the request payload for each input text.
        """
        for text in texts:
            yield {"inputText": text}

    def parse_response(self, response_body: bytes) -> List[float]:
        """
        Parses the response body from Titan to extract the embedding vector.
        Args:
            response_body: The raw bytes of the response body from Titan.
        Returns:
            A list of floats representing the embedding vector.
        Raises:
            ValueError: If the response does not contain a valid embedding.
        """
        result = json.loads(response_body)
        embedding = result.get("embedding")

        if not embedding:
            raise ValueError("No embedding returned from model")

        return embedding


class EmbeddingsProcessor:
    """
    Handles embedding generation with retry logic and concurrency for Titan models.
    Designed for use in a document chunking pipeline but can be used
    in other contexts where batch embedding generation is needed.
    """

    def __init__(
        self,
        model_id: str = "amazon.titan-embed-text-v2:0",
        region: str = "us-east-1",
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_workers: int = 10,
        read_timeout: int = 60,
        connect_timeout: int = 10,
        adapter: Optional[TitanEmbeddingAdapter] = None,
    ):
        self.model_id = model_id
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_workers = max_workers
        self.adapter = adapter or TitanEmbeddingAdapter()

        # Pool size is set to 2x workers so threads never queue
        # waiting for a connection. Without this, scaling max_workers
        # beyond the default pool size (10) degrades performance.
        config = Config(
            max_pool_connections=max_workers * 2,
            read_timeout=read_timeout,
            connect_timeout=connect_timeout,
        )

        self.bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=config,
        )

    def get_embedding(self, text: str) -> List[float]:
        """
        Convenience method for embedding a single text input.
        Args:
            text: The input string to be embedded.
        Returns:
            A list of floats representing the embedding vector for the input text.
        Raises:
            RuntimeError: If embedding generation fails after retries.
        """
        result = self.embed_batch([text])
        result.raise_on_errors()
        return result.embeddings[0]

    def embed_batch(self, texts: List[str]) -> BatchEmbeddingResult:
        """
        Concurrent embedding execution.

        Payloads are streamed from the adapter generator so memory
        usage stays flat regardless of batch size — no intermediate
        list duplication.

        Throttle events are counted and surfaced in BatchEmbeddingResult
        so callers and monitoring systems can react to sustained pressure.
        Args:
            texts: A list of input strings to be embedded.
        Returns:
            A BatchEmbeddingResult containing embeddings, errors, and throttle count.
        Raises:
            RuntimeError: If embedding generation fails after retries.
        """
        embeddings: List[Optional[List[float]]] = [None] * len(texts)
        errors: Dict[int, Exception] = {}
        throttle_count = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._invoke_with_retry, payload): idx
                for idx, payload in enumerate(
                    self.adapter.build_requests(texts)
                )
            }

            for future in as_completed(futures):
                idx = futures[future]

                try:
                    raw_response, request_throttles = future.result()
                    throttle_count += request_throttles
                    embeddings[idx] = self.adapter.parse_response(raw_response)

                except Exception as exc:
                    logger.error("Embedding failed at index %d: %s", idx, exc)
                    errors[idx] = exc

        if throttle_count:
            logger.warning(
                "Batch completed with %d throttle event(s) across %d request(s). "
                "Consider reducing max_workers or implementing adaptive concurrency.",
                throttle_count,
                len(texts),
            )

        return BatchEmbeddingResult(
            embeddings=embeddings,
            errors=errors,
            throttle_count=throttle_count,
        )

    def _invoke_with_retry(self, payload: Dict[str, Any]) -> tuple:
        """
        Returns (response_body, throttle_count) so the caller can
        aggregate throttle events across concurrent futures without
        shared mutable state.
        Args:
            payload: The request payload to send to the model.
        Returns:
            A tuple containing the raw response body and the
            number of throttle events encountered.
        Raises:
            RuntimeError: If embedding generation fails after retries.
        """
        backoff = self.initial_backoff
        throttle_count = 0

        for attempt in range(self.max_retries):
            try:
                response = self.bedrock_client.invoke_model(
                    modelId=self.model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(payload),
                )

                return response["body"].read(), throttle_count

            except ClientError as e:
                error_code = e.response["Error"]["Code"]

                retryable = error_code in RETRYABLE_ERROR_CODES
                last_attempt = attempt == self.max_retries - 1

                if not retryable or last_attempt:
                    raise

                if error_code == "ThrottlingException":
                    throttle_count += 1

                sleep_time = backoff * (0.5 + random.random())

                logger.warning(
                    "Retryable error %s — retry %d/%d in %.2fs",
                    error_code,
                    attempt + 1,
                    self.max_retries,
                    sleep_time,
                )

                time.sleep(sleep_time)
                backoff *= 2

        raise RuntimeError("Retry loop exited unexpectedly")
