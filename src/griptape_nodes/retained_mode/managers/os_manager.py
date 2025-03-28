import os
import subprocess
import sys
from pathlib import Path

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.os_events import (
    OpenAssociatedFileRequest,
    OpenAssociatedFileResultFailure,
    OpenAssociatedFileResultSuccess,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager


class OSManager:
    """A class to manage OS-level scenarios.

    Making its own class as some runtime environments and some customer requirements may dictate this as optional.
    This lays the groundwork to exclude specific functionality on a configuration basis.
    """

    def __init__(self, event_manager: EventManager):
        event_manager.assign_manager_to_request_type(
            request_type=OpenAssociatedFileRequest, callback=self.on_open_associated_file_request
        )

    def on_open_associated_file_request(self, request: OpenAssociatedFileRequest) -> ResultPayload:  # noqa: PLR0911
        # Sanitize and validate the file path
        try:
            path = Path(request.path_to_file).resolve(strict=True)
        except (ValueError, RuntimeError):
            details = f"Invalid file path: '{request.path_to_file}'"
            print(details)  # TODO(griptape): Move to Log
            return OpenAssociatedFileResultFailure()

        if not path.exists() or not path.is_file():
            details = f"File does not exist: '{path}'"
            print(details)  # TODO(griptape): Move to Log
            return OpenAssociatedFileResultFailure()

        print(f"Attempting to open: {path} on platform: {sys.platform}")

        try:
            platform_name = sys.platform
            if platform_name.startswith("win"):
                # Linter complains but this is the recommended way on Windows
                # We can ignore this warning as we've validated the path
                os.startfile(str(path))  # noqa: S606 # pyright: ignore[reportAttributeAccessIssue]
                print(f"Started file on Windows: {path}")
            elif platform_name.startswith("darwin"):
                # On macOS, open should be in a standard location
                subprocess.run(  # noqa: S603
                    ["/usr/bin/open", str(path)],
                    check=True,  # Explicitly use check
                    capture_output=True,
                    text=True,
                )
                print(f"Opened file on macOS: {path}")
            elif platform_name.startswith("linux"):
                # Use full path to xdg-open to satisfy linter
                # Common locations for xdg-open:
                xdg_paths = ["/usr/bin/xdg-open", "/bin/xdg-open", "/usr/local/bin/xdg-open"]

                xdg_path = next((p for p in xdg_paths if Path(p).exists()), None)
                if not xdg_path:
                    print("xdg-open not found in standard locations")
                    return OpenAssociatedFileResultFailure()

                subprocess.run(  # noqa: S603
                    [xdg_path, str(path)],
                    check=True,  # Explicitly use check
                    capture_output=True,
                    text=True,
                )
                print(f"Opened file on Linux: {path}")
            else:
                details = f"Unsupported platform: '{platform_name}'"
                print(details)  # TODO(griptape): Move to Log
                return OpenAssociatedFileResultFailure()

            return OpenAssociatedFileResultSuccess()
        except subprocess.CalledProcessError as e:
            print(f"Process error when opening file: {e.stderr}")
            return OpenAssociatedFileResultFailure()
        except Exception as e:
            print(f"Exception occurred when trying to open file: {type(e).__name__}: {e}")
            return OpenAssociatedFileResultFailure()
