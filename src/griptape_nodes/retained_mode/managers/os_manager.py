import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.os_events import (
    OpenAssociatedFileRequest,
    OpenAssociatedFileResultFailure,
    OpenAssociatedFileResultSuccess,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager

console = Console()
logger = logging.getLogger("griptape_nodes")


class OSManager:
    """A class to manage OS-level scenarios.

    Making its own class as some runtime environments and some customer requirements may dictate this as optional.
    This lays the groundwork to exclude specific functionality on a configuration basis.
    """

    def __init__(self, event_manager: EventManager | None = None):
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                request_type=OpenAssociatedFileRequest, callback=self.on_open_associated_file_request
            )

    @staticmethod
    def platform() -> str:
        return sys.platform

    @staticmethod
    def is_windows() -> bool:
        return sys.platform.startswith("win")

    @staticmethod
    def is_mac() -> bool:
        return sys.platform.startswith("darwin")

    @staticmethod
    def is_linux() -> bool:
        return sys.platform.startswith("linux")

    def replace_process(self, args: list[Any]) -> None:
        """Replace the current process with a new one.

        Args:
            args: The command and arguments to execute.
        """
        if self.is_windows():
            # excecvp is a nightmare on Windows, so we use subprocess.Popen instead
            # https://stackoverflow.com/questions/7004687/os-exec-on-windows
            subprocess.Popen(args)  # noqa: S603
            sys.exit(0)
        else:
            sys.stdout.flush()  # Recommended here https://docs.python.org/3/library/os.html#os.execvpe
            os.execvp(args[0], args)  # noqa: S606

    def on_open_associated_file_request(self, request: OpenAssociatedFileRequest) -> ResultPayload:  # noqa: PLR0911
        # Sanitize and validate the file path
        try:
            path = Path(request.path_to_file).resolve(strict=True)
        except (ValueError, RuntimeError):
            details = f"Invalid file path: '{request.path_to_file}'"
            logger.info(details)
            return OpenAssociatedFileResultFailure()

        if not path.exists() or not path.is_file():
            details = f"File does not exist: '{path}'"
            logger.info(details)
            return OpenAssociatedFileResultFailure()

        logger.info("Attempting to open: %s on platform: %s", path, sys.platform)

        try:
            platform_name = sys.platform
            if self.is_windows:
                # Linter complains but this is the recommended way on Windows
                # We can ignore this warning as we've validated the path
                os.startfile(str(path))  # noqa: S606 # pyright: ignore[reportAttributeAccessIssue]
                logger.info("Started file on Windows: %s", path)
            elif self.is_mac:
                # On macOS, open should be in a standard location
                subprocess.run(  # noqa: S603
                    ["/usr/bin/open", str(path)],
                    check=True,  # Explicitly use check
                    capture_output=True,
                    text=True,
                )
                logger.info("Started file on macOS: %s", path)
            elif self.is_linux:
                # Use full path to xdg-open to satisfy linter
                # Common locations for xdg-open:
                xdg_paths = ["/usr/bin/xdg-open", "/bin/xdg-open", "/usr/local/bin/xdg-open"]

                xdg_path = next((p for p in xdg_paths if Path(p).exists()), None)
                if not xdg_path:
                    logger.info("xdg-open not found in standard locations")
                    return OpenAssociatedFileResultFailure()

                subprocess.run(  # noqa: S603
                    [xdg_path, str(path)],
                    check=True,  # Explicitly use check
                    capture_output=True,
                    text=True,
                )
                logger.info("Started file on Linux: %s", path)
            else:
                details = f"Unsupported platform: '{platform_name}'"
                logger.info(details)
                return OpenAssociatedFileResultFailure()

            return OpenAssociatedFileResultSuccess()
        except subprocess.CalledProcessError as e:
            logger.error("Process error when opening file: %s", e.stderr)
            return OpenAssociatedFileResultFailure()
        except Exception as e:
            logger.error("Exception occurred when trying to open file: %s", type(e).__name__)
            return OpenAssociatedFileResultFailure()
