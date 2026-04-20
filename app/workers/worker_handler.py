import os
import logging
import time
import threading
import boto3
from dataclasses import dataclass, field
from typing import Type

from django.db import close_old_connections

from workers.handler import Handler


@dataclass
class WorkerHandler:
    """
    WorkerHandler is responsible for consuming messages from an SQS queue,
    delegating processing to a Handler, and managing the message lifecycle
    (including visibility timeouts, retries, and deletion).

    Responsibilities:
        - SQS polling
        - concurrency control
        - visibility timeout heartbeat
        - message deletion
        - lifecycle orchestration
    """

    queue_url: str
    visibility_timeout: int
    processor: Type[Handler]
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger(__name__)
    )

    def __post_init__(self):
        self._stop_event = threading.Event()
        self._sqs = boto3.client(
            "sqs",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        self._max_retries = int(os.environ.get("MAX_RETRIES", "5"))

    def stop(self, *args) -> None:
        """
        Designed to be used as a signal handler for SIGINT and SIGTERM,
        gracefully stop the worker by signaling the main loop to exit.
        Ongoing message processing will be allowed to complete, but no new
        messages will be fetched from SQS.
            Args:
                *args: signal handler signature (signum, frame), ignored here.
            Returns:
                None
        """
        self.logger.info("Shutdown signal received, stopping gracefully...")
        self._stop_event.set()

    def _heartbeat_loop(
        self, receipt_handle: str, done_event: threading.Event
    ) -> None:
        """
        Periodically extend the visibility timeout of the message being processed
        until processing is done or the worker is stopped.
        Args:
            receipt_handle: The SQS receipt handle of the message being processed.
            done_event: A threading.Event that signals when processing is complete.
        Returns:
            None
        """
        interval = min(max(self.visibility_timeout // 2, 10), 60)

        while not done_event.wait(interval):
            if self._stop_event.is_set():
                return

            try:
                self._sqs.change_message_visibility(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=receipt_handle,
                    VisibilityTimeout=self.visibility_timeout,
                )
                self.logger.debug("Visibility timeout extended")
            except Exception:
                self.logger.warning(
                    "Could not extend visibility timeout",
                    exc_info=True,
                )

    def _process_message(self, message: dict) -> None:
        """
        Process a single SQS message using the provided Handler.
        Implements retry logic based on the ApproximateReceiveCount attribute.
        Args:
            message: The SQS message to process.
        Returns:
            None
        """
        message_id = message["MessageId"]
        receipt_handle = message["ReceiptHandle"]

        attributes = message.get("Attributes", {})
        receive_count = int(attributes.get("ApproximateReceiveCount", 1))

        self.logger.info(
            f"Processing message {message_id} (attempt {receive_count})"
        )

        if receive_count >= self._max_retries:
            self.logger.error(
                f"Message {message_id} exceeded max retries ({self._max_retries})"
            )
            try:
                self._sqs.delete_message(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=receipt_handle,
                )
            except Exception:
                self.logger.exception(
                    "Failed to delete message after max retries"
                )
            return

        done_event = threading.Event()

        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(receipt_handle, done_event),
            daemon=True,
        )
        heartbeat_thread.start()

        processor = self.processor()
        success = False

        try:
            close_old_connections()

            processor.handle(message)

            try:
                self._sqs.delete_message(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=receipt_handle,
                )
            except Exception:
                self.logger.exception("Failed to delete message from SQS")
                raise  # fuerza retry

            success = True

        except Exception as e:
            self.logger.exception(f"Failed to process message {message_id}")

            try:
                processor.on_error(message, e)
            except Exception:
                self.logger.warning(
                    "Error in processor.on_error",
                    exc_info=True,
                )

        finally:
            done_event.set()
            heartbeat_thread.join()

            if success:
                try:
                    processor.on_success(message)
                except Exception:
                    self.logger.warning(
                        "Error in processor.on_success",
                        exc_info=True,
                    )

            try:
                processor.cleanup()
            except Exception:
                self.logger.warning(
                    "Error during processor cleanup",
                    exc_info=True,
                )

            close_old_connections()

    def run(self) -> None:
        """
        Main loop for the worker. Continuously polls SQS for messages and processes them
        until a shutdown signal is received.
        """
        self.logger.info("Single-thread worker started")

        backoff = 5
        max_backoff = 60

        while not self._stop_event.is_set():
            try:
                response = self._sqs.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=20,
                    VisibilityTimeout=self.visibility_timeout,
                    AttributeNames=["ApproximateReceiveCount"],
                )
                backoff = 5  # reset al recibir respuesta exitosa

            except Exception:
                self.logger.exception("Error receiving messages from SQS")
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
                continue

            messages = response.get("Messages", [])

            if not messages:
                continue

            for msg in messages:
                if self._stop_event.is_set():
                    break

                self._process_message(msg)

        self.logger.info("Worker stopped")
