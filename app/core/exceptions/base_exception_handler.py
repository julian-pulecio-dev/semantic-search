import asyncio
from abc import ABC, abstractmethod
from functools import wraps


class BaseErrorHandler(ABC):
    """
    Base class for decorators that translate low-level exceptions into
    domain exceptions.

    Subclasses define which exception types to intercept via `catches`,
    and how to map them via `handle`. The __call__ implementation wraps
    any sync or async function transparently.

    Usage:
        class MyErrorHandler(BaseErrorHandler):
            catches = (SomeLowLevelError,)

            def handle(self, exc):
                return MyDomainError(str(exc))

        handle_my_errors = MyErrorHandler()

        @handle_my_errors
        def my_function():
            ...
    """

    @property
    @abstractmethod
    def catches(self) -> tuple[type[Exception], ...]:
        """Exception types this handler intercepts."""
        ...

    @abstractmethod
    def handle(self, exc: Exception) -> Exception:
        """
        Receives the caught exception and returns the domain exception
        to raise in its place.
        Args:
            exc: The original low-level exception.
        Returns:
            A domain exception instance to raise instead.
        """
        ...

    def __call__(self, func):
        handler = self

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except handler.catches as e:
                raise handler.handle(e) from e

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except handler.catches as e:
                raise handler.handle(e) from e

        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper
