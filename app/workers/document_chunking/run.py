import os
import sys
import signal
import logging

from workers.worker_handler import WorkerHandler
from workers.document_chunking.document_chunking_handler import (
    DocumentChunkingHandler,
)


def setup_django():
    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        sys.path.insert(0, os.getcwd())
        os.environ.setdefault(
            "DJANGO_SETTINGS_MODULE",
            "app.settings.local",
        )
        import django

        django.setup()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    setup_django()

    processor = DocumentChunkingHandler()

    worker = WorkerHandler(
        queue_url=os.environ["SQS_QUEUE_URL"],
        max_workers=int(os.environ.get("MAX_WORKERS", "4")),
        visibility_timeout=int(os.environ.get("VISIBILITY_TIMEOUT", "300")),
        processor=processor,
    )

    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)

    worker.run()
