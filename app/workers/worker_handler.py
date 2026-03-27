import os
import logging
import time
import threading
import boto3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from workers.handler import Handler


def close_db_connections():
    from django.db import connections

    connections.close_all()


@dataclass
class WorkerHandler:
    queue_url: str
    max_workers: int
    visibility_timeout: int
    processor: Handler
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger(__name__)
    )

    def __post_init__(self):
        self._stop_event = threading.Event()
        self._semaphore = threading.Semaphore(self.max_workers)
        self._local = threading.local()

    def stop(self, *args):
        self.logger.info("Shutdown signal received, stopping gracefully...")
        self._stop_event.set()

    def _get_sqs_client(self):
        if not hasattr(self._local, "sqs"):
            session = boto3.session.Session()
            self._local.sqs = session.client(
                "sqs",
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
        return self._local.sqs

    def _heartbeat_loop(self, sqs, receipt_handle, done_event):
        interval = max(self.visibility_timeout // 2, 30)

        while not done_event.wait(interval):
            if self._stop_event.is_set():
                return

            try:
                sqs.change_message_visibility(
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

    def _process_message(self, message):
        sqs = self._get_sqs_client()

        message_id = message["MessageId"]
        receipt_handle = message["ReceiptHandle"]

        done_event = threading.Event()

        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(sqs, receipt_handle, done_event),
            daemon=True,
        )
        heartbeat_thread.start()

        try:
            self.logger.info(f"Processing message {message_id}")

            self.processor.handle(message)

            sqs.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
            )

            self.processor.on_success(message)

            self.logger.info(f"Completed message {message_id}")

        except Exception as e:
            self.logger.exception(f"Failed to process message {message_id}")
            self.processor.on_error(message, e)

        finally:
            done_event.set()
            heartbeat_thread.join(timeout=1)
            self.processor.cleanup()

    def _process_wrapper(self, message):
        try:
            self._process_message(message)
        finally:
            self._semaphore.release()

    def _acquire_available_slots(self):
        active_workers = self.max_workers - self._semaphore._value
        dynamic_cap = max(1, active_workers)
        cap = min(dynamic_cap, self.max_workers)

        slots = 0
        while slots < cap:
            if not self._semaphore.acquire(timeout=0):
                break
            slots += 1

        return slots

    def run(self):
        self.logger.info(f"Worker started (MAX_WORKERS={self.max_workers})")

        sqs = self._get_sqs_client()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while not self._stop_event.is_set():
                available_slots = self._acquire_available_slots()

                if available_slots == 0:
                    time.sleep(0.2)
                    continue

                batch_size = min(available_slots, 10)

                try:
                    response = sqs.receive_message(
                        QueueUrl=self.queue_url,
                        MaxNumberOfMessages=batch_size,
                        WaitTimeSeconds=20,
                        VisibilityTimeout=self.visibility_timeout,
                        AttributeNames=["ApproximateReceiveCount"],
                    )
                except Exception:
                    self.logger.exception("Error receiving messages from SQS")

                    for _ in range(available_slots):
                        self._semaphore.release()

                    time.sleep(5)
                    continue

                messages = response.get("Messages", [])

                unused_slots = available_slots - len(messages)
                for _ in range(unused_slots):
                    self._semaphore.release()

                for msg in messages:
                    executor.submit(self._process_wrapper, msg)

        self.logger.info("Worker stopped")
