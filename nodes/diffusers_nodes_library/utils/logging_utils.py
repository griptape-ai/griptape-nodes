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
