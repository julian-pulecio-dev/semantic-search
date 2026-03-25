import os
import sys
import json
import signal
import logging
import time
import django
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.local")

django.setup()

logger = logging.getLogger(__name__)

QUEUE_URL = os.environ["SQS_QUEUE_URL"]
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "4"))
VISIBILITY_TIMEOUT = int(os.environ.get("VISIBILITY_TIMEOUT", "300"))

sqs = boto3.client(
    "sqs", region_name=os.environ.get("AWS_REGION", "us-east-1")
)

running = True


def handle_signal(signum, frame):
    global running
    running = False
    logger.info("Shutdown signal received, finishing current batch...")


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def process_message(message):
    message_id = message["MessageId"]
    try:
        body = json.loads(message["Body"])
        logger.info(f"Processing message {message_id}: {body}")

        # TODO: document chunking logic here
        time.sleep(60)

        sqs.delete_message(
            QueueUrl=QUEUE_URL,
            ReceiptHandle=message["ReceiptHandle"],
        )
        logger.info(f"Completed message {message_id}")
    except Exception:
        logger.exception(
            f"Failed to process message {message_id} — will retry after \
                visibility timeout"
        )


def run():
    logger.info(f"Worker started (MAX_WORKERS={MAX_WORKERS})")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while running:
            response = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=MAX_WORKERS,
                WaitTimeSeconds=20,
                VisibilityTimeout=VISIBILITY_TIMEOUT,
            )
            messages = response.get("Messages", [])
            if not messages:
                continue

            futures = {
                executor.submit(process_message, msg): msg["MessageId"]
                for msg in messages
            }
            for future in as_completed(futures):
                future.result()

    logger.info("Worker stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run()
