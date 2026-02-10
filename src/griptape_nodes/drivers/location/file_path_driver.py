"""Driver for file system path locations."""

from pathlib import Path

from griptape_nodes.drivers.location.base_location_driver import BaseLocationDriver
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    WriteFileRequest,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class FilePathDriver(BaseLocationDriver):
    """Driver for file system path locations.

    Acts as a fallback driver - always returns True from can_handle().
    Must be registered last (lowest priority) in the driver registry.
    """

    def can_handle(self, location: str) -> bool:  # noqa: ARG002
        """Check if location is a file path.

        Always returns True to act as fallback for any unhandled location.

        Args:
            location: Location string to check

        Returns:
            Always True (fallback provider)
        """
        return True

    async def aload(self, location: str, timeout: float = 120.0) -> bytes:  # noqa: ASYNC109, ARG002
        """Read file from filesystem.

        Args:
            location: Path to file
            timeout: Ignored for file system operations

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file does not exist
            RuntimeError: If read operation fails
        """
        path = Path(location)

        if not path.exists():
            error_msg = f"File not found: {location}"
            raise FileNotFoundError(error_msg)

        try:
            return path.read_bytes()
        except Exception as e:
            error_msg = f"Failed to read file {location}: {e}"
            raise RuntimeError(error_msg) from e

    async def asave(self, location: str, data: bytes, existing_file_policy: str) -> str:
        """Write file to filesystem.

        Args:
            location: Path to file
            data: File content as bytes
            existing_file_policy: How to handle existing files (OVERWRITE, CREATE_NEW, FAIL)

        Returns:
            File path (or local server URL if available)

        Raises:
            FileExistsError: If file exists and policy is FAIL
            RuntimeError: If write operation fails
        """
        policy = ExistingFilePolicy(existing_file_policy)

        write_request = WriteFileRequest(
            file_path=location,
            content=data,
            existing_file_policy=policy,
        )

        result = GriptapeNodes.OSManager().on_write_file_request(write_request)

        if not isinstance(result, WriteFileResultSuccess):
            error_msg = f"Failed to write file {location}: {result.result_details}"
            raise RuntimeError(error_msg)  # noqa: TRY004

        return result.final_file_path
