import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

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


class DiskSpaceInfo(NamedTuple):
    """Disk space information in bytes."""

    total: int
    used: int
    free: int


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
            logger.error(
                "Process error when opening file: return code=%s, stdout=%s, stderr=%s",
                e.returncode,
                e.stdout,
                e.stderr,
            )
            return OpenAssociatedFileResultFailure()
        except Exception as e:
            logger.error("Exception occurred when trying to open file: %s", type(e).__name__)
            return OpenAssociatedFileResultFailure()

    @staticmethod
    def get_disk_space_info(path: Path) -> DiskSpaceInfo:
        """Get disk space information for a given path.

        Args:
            path: The path to check disk space for.

        Returns:
            DiskSpaceInfo with total, used, and free disk space in bytes.
        """
        stat = shutil.disk_usage(path)
        return DiskSpaceInfo(total=stat.total, used=stat.used, free=stat.free)

    @staticmethod
    def check_available_disk_space(path: Path, required_gb: float) -> bool:
        """Check if there is sufficient disk space available.

        Args:
            path: The path to check disk space for.
            required_gb: The minimum disk space required in GB.

        Returns:
            True if sufficient space is available, False otherwise.
        """
        try:
            disk_info = OSManager.get_disk_space_info(path)
            required_bytes = int(required_gb * 1024 * 1024 * 1024)  # Convert GB to bytes
            return disk_info.free >= required_bytes  # noqa: TRY300
        except OSError:
            return False

    @staticmethod
    def format_disk_space_error(path: Path, exception: Exception | None = None) -> str:
        """Format a user-friendly disk space error message.

        Args:
            path: The path where the disk space issue occurred.
            exception: The original exception, if any.

        Returns:
            A formatted error message with disk space information.
        """
        try:
            disk_info = OSManager.get_disk_space_info(path)
            free_gb = disk_info.free / (1024**3)
            used_gb = disk_info.used / (1024**3)
            total_gb = disk_info.total / (1024**3)

            error_msg = f"Insufficient disk space at {path}. "
            error_msg += f"Available: {free_gb:.2f} GB, Used: {used_gb:.2f} GB, Total: {total_gb:.2f} GB. "

            if exception:
                error_msg += f"Error: {exception}"
            else:
                error_msg += "Please free up disk space and try again."

            return error_msg  # noqa: TRY300
        except OSError:
            return f"Disk space error at {path}. Unable to retrieve disk space information."
