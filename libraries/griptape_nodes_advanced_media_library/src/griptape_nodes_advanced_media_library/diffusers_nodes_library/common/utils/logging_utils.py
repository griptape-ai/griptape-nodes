import logging
import sys
from collections.abc import Callable
from types import TracebackType


class StdoutCapture:
    def __init__(self, callback: Callable[[str], None]) -> None:
        self.callback: Callable[[str], None] = callback
        self._original_stdout = sys.stdout

    def write(self, data: str) -> None:
        self._original_stdout.write(data)
        self._original_stdout.flush()
        self.callback(data)

    def flush(self) -> None:
        self._original_stdout.flush()

    def __enter__(self) -> "StdoutCapture":
        sys.stdout = self
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
    ) -> None:
        sys.stdout = self._original_stdout


class CallbackHandler(logging.Handler):
    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__(level=logging.INFO)
        self.callback = callback
        self.setFormatter(logging.Formatter("%(message)s\n"))

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.callback(message)


class LoggerCapture:
    def __init__(
        self, logger: logging.Logger, callback: Callable[[str], None], level: int | str = logging.INFO
    ) -> None:
        self.logger = logger
        self.target_level = level
        self._handler = CallbackHandler(callback)

    def __enter__(self) -> "LoggerCapture":
        self.original_level = self.logger.level
        self.logger.setLevel(self.target_level)
        self.logger.addHandler(self._handler)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.logger.removeHandler(self._handler)
        self.logger.setLevel(self.original_level)


def seconds_to_human_readable(seconds: float) -> str:
    """Convert seconds to a human-readable format.

    Args:
        seconds (float): The number of seconds to convert.

    Returns:
        str: A human-readable string representing the time duration.
    """
    intervals = (
        ("year", 31536000),
        ("month", 2592000),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
        ("millisecond", 0.001),
    )

    for name, count in intervals:
        if seconds >= count:
            value = seconds / count
            return f"{value:.2f} {name}{'s' if value != 1 else ''}"
    return "0.00 milliseconds"
