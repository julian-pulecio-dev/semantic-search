import os
import logging
import signal
from typing import Type


class WorkerRunner:
    """
    WorkerRunner is the entry point for running a worker process. It sets up
    the environment, initializes logging, and starts the WorkerHandler with the
    specified Handler class.

    Responsibilities:
        - environment setup (Django, logging, etc.)
        - signal handling for graceful shutdown
        - worker initialization and execution
    """
    def __init__(self):
        self.logger = self._setup_logging()
        self.logger.info("Initializing logging...")

        self.logger.info("Initializing Django...")
        self._setup_django()

    def _setup_logging(self) -> logging.Logger:
        """
        Configure logging based on environment variables and return a logger instance.
        Returns:
            logging.Logger: Configured logger instance for the worker.
        """
        level = getattr(
            logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO
        )
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] [%(process)d] %(message)s",
        )
        return logging.getLogger(__name__)

    def _setup_django(self) -> None:
        """
        Set up Django environment for the worker process. This is necessary to use
        Django models and other components within the Handler logic.
        Returns:
            None
        """
        import django
        from django.conf import settings

        if not settings.configured:
            os.environ.setdefault(
                "DJANGO_SETTINGS_MODULE", "app.settings.local"
            )
            django.setup()

    def _get_int_env(self, name: str, default: int) -> int:
        """
        Helper method to read an integer environment variable with
        a default value.
        Args:
            name: The name of the environment variable to read.
            default: The default value to return if the environment
            variable is not set.
        Returns:
            int: The integer value of the environment variable, or
            the default if not set.
        Raises:
            RuntimeError: If the environment variable is set but
            cannot be converted to an integer.
        """

        raw = os.environ.get(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            raise RuntimeError(f"{name} must be an integer, got: {raw}")

    def run(self, processor_cls: Type):
        """
        Run the worker with the specified Handler class for
        processing messages.
        Args:
            processor_cls: The Handler subclass that contains the
            business logic for processing messages.
        Returns:
            None
        """
        from workers.worker_handler import WorkerHandler

        queue_url = os.environ.get("SQS_QUEUE_URL")
        if not queue_url:
            raise RuntimeError("SQS_QUEUE_URL is required")

        visibility_timeout = self._get_int_env("VISIBILITY_TIMEOUT", 300)

        self.logger.info(
            f"Starting worker | \
              queue={queue_url} | \
              visibility_timeout={visibility_timeout} | \
              processor={processor_cls.__name__}"
        )

        worker = WorkerHandler(
            queue_url=queue_url,
            visibility_timeout=visibility_timeout,
            processor=processor_cls,
        )

        def _handle_shutdown(signum, frame):
            self.logger.info(f"Signal {signum} received. Stopping worker...")
            worker.stop()

        signal.signal(signal.SIGTERM, _handle_shutdown)
        signal.signal(signal.SIGINT, _handle_shutdown)

        try:
            worker.run()
        except Exception:
            self.logger.exception("Worker crashed")
            raise
        finally:
            self.logger.info("Worker stopped")
