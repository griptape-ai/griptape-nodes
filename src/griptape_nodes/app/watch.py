from __future__ import annotations

import subprocess
import sys
import time
from typing import Any

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from griptape_nodes.utils.uv_utils import find_uv_bin


class ReloadHandler(PatternMatchingEventHandler):
    def __init__(
        self,
        *,
        patterns: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
        ignore_directories: bool = False,
        case_sensitive: bool = False,
    ) -> None:
        super().__init__(
            patterns=patterns,
            ignore_patterns=ignore_patterns,
            ignore_directories=ignore_directories,
            case_sensitive=case_sensitive,
        )
        self.process = None
        self.start_process()

    def start_process(self) -> None:
        if self.process:
            self.process.terminate()
        uv_path = find_uv_bin()
        self.process = subprocess.Popen(  # noqa: S603
            [uv_path, "run", "gtn"],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

    def on_modified(self, event: Any) -> None:
        """Called on any file event in the watched directory (create, modify, delete, move)."""
        # Don't reload if the event is on a directory
        if event.is_directory:
            return

        if str(event.src_path).endswith(__file__):
            return

        self.start_process()


if __name__ == "__main__":
    event_handler = ReloadHandler(patterns=["*.py"], ignore_patterns=["*.pyc", "*.pyo"], ignore_directories=True)

    observer = Observer()
    observer.schedule(event_handler, path="src", recursive=True)
    observer.schedule(event_handler, path="libraries", recursive=True)
    observer.schedule(event_handler, path="tests", recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if event_handler.process:
            event_handler.process.terminate()
    finally:
        observer.stop()
        observer.join()
