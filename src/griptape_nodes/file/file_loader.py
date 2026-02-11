"""Read-only file loader for multi-backend sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from griptape_nodes.retained_mode.events.os_events import (
    FileIOFailureReason,
    ReadFileRequest,
    ReadFileResultFailure,
    ReadFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@dataclass
class FileLoader:
    """Read-only file loader for multi-backend sources.

    Loads files from any backend: local paths, HTTP URLs, S3 buckets,
    Griptape Cloud, or data URIs. Uses OSManager's unified ReadFileRequest system.

    For WRITING files, use OSManager directly (all saves go to local filesystem).

    Examples:
        # Local file
        loader = FileLoader(location="/tmp/test.txt")
        data = await loader.read()

        # HTTP URL
        loader = FileLoader(location="https://example.com/image.png")
        image_data = await loader.read()

        # S3 bucket
        loader = FileLoader(location="s3://bucket/key.txt")
        s3_data = await loader.read()

        # Data URI
        loader = FileLoader(location="data:image/png;base64,...")
        decoded_data = await loader.read()
    """

    location: str  # "/path/to/file", "s3://bucket/key", "https://...", etc.

    async def read(self, timeout: float = 120.0) -> bytes:  # noqa: ASYNC109, ARG002
        """Read bytes from location using OSManager's unified read system.

        Args:
            timeout: Timeout in seconds for the operation (default: 120)

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: File does not exist
            PermissionError: No permission to read file
            OSError: I/O error occurred
        """
        # Use OSManager's unified read system
        request = ReadFileRequest(
            file_path=self.location,
            workspace_only=False,  # Allow reading from anywhere
            should_transform_image_content_to_thumbnail=False,  # Get raw bytes
        )

        result = await GriptapeNodes.OSManager().on_read_file_request(request)

        # Convert result to appropriate exception or return bytes
        if isinstance(result, ReadFileResultFailure):
            if result.failure_reason == FileIOFailureReason.FILE_NOT_FOUND:
                raise FileNotFoundError(result.result_details)
            if result.failure_reason == FileIOFailureReason.PERMISSION_DENIED:
                raise PermissionError(result.result_details)
            raise OSError(result.result_details)

        # Type narrowing - at this point we know it's ReadFileResultSuccess
        result = cast("ReadFileResultSuccess", result)

        # Return content as bytes
        if isinstance(result.content, bytes):
            return result.content
        if isinstance(result.content, str):
            return result.content.encode(result.encoding or "utf-8")
        msg = f"Unexpected content type: {type(result.content)}"
        raise TypeError(msg)

    async def exists(self) -> bool:
        """Check if file exists and is readable.

        Returns:
            True if file exists and is readable
        """
        try:
            await self.read()
        except (FileNotFoundError, Exception):
            return False
        else:
            return True

    async def size(self) -> int:
        """File size in bytes.

        Raises:
            FileNotFoundError: File does not exist
        """
        # Read and return length (could optimize with head-only request in future)
        content = await self.read()
        return len(content)
