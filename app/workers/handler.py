from abc import ABC, abstractmethod
from typing import Any, Dict


class Handler(ABC):
    """
    Base contract for any processing logic executed by WorkerHandler.

    Responsibilities separation:
        - business logic
        - message interpretation
        - external integrations (DB, APIs, etc.)
    """

    @abstractmethod
    def handle(self, message: Dict[str, Any]) -> None:
        """
        Process a single SQS message.

        Must raise an Exception if processing fails.
        The worker will decide retry behavior by
        leaving the message in the queue.
        """
        pass

    def on_success(self, message: Dict[str, Any]) -> None:
        """
        Called after successful processing and after the
        message has been deleted from SQS.

        Useful for:
            - metrics
            - logging
            - side effects
        """
        pass

    def on_error(
        self,
        message: Dict[str, Any],
        exception: Exception,
    ) -> None:
        """
        Called when handle() raises an exception.

        Useful for:
            - error reporting (Sentry, Datadog, etc.)
            - custom logging
            - alerting
        """
        pass

    def cleanup(self) -> None:
        """
        Always executed at the end of processing
        (both success and failure).

        Useful for:
            - closing DB connections
            - clearing thread-local resources
        """
        pass
