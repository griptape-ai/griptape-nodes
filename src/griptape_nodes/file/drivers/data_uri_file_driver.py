"""File driver for data URI locations."""

import base64

from griptape_nodes.file.base_file_driver import BaseFileDriver


class DataUriFileDriver(BaseFileDriver):
    """Read-only file driver for data URI locations.

    Handles locations starting with "data:" prefix, decoding base64-encoded data.
    Example: "data:image/png;base64,iVBORw0KGgo..."
    """

    def can_handle(self, location: str) -> bool:
        """Check if location is a data URI.

        Args:
            location: Location string to check

        Returns:
            True if location starts with "data:"
        """
        return location.startswith("data:")

    async def read(self, location: str, timeout: float) -> bytes:  # noqa: ARG002, ASYNC109
        """Decode data URI to bytes.

        Args:
            location: Data URI string (e.g., "data:image/png;base64,...")
            timeout: Ignored for data URIs (no network operation)

        Returns:
            Decoded bytes

        Raises:
            ValueError: If data URI is malformed or base64 decoding fails
        """
        if not location.startswith("data:"):
            msg = f"Invalid data URI: must start with 'data:', got: {location[:50]}"
            raise ValueError(msg)

        if ";base64," not in location:
            msg = f"Invalid data URI: must contain ';base64,', got: {location[:100]}"
            raise ValueError(msg)

        _, b64_data = location.split(";base64,", 1)

        try:
            return base64.b64decode(b64_data)
        except Exception as e:
            msg = f"Failed to decode base64 data from data URI: {e}"
            raise ValueError(msg) from e

    async def exists(self, location: str) -> bool:
        """Data URIs always "exist" if they can be decoded.

        Args:
            location: Data URI string

        Returns:
            True if the data URI is valid and can be decoded
        """
        try:
            await self.read(location, 0)
        except Exception:
            return False
        else:
            return True

    def get_size(self, location: str) -> int:
        """Get decoded size of data URI.

        Args:
            location: Data URI string

        Returns:
            Size in bytes of the decoded data

        Raises:
            ValueError: If data URI is malformed
        """
        if ";base64," not in location:
            msg = f"Invalid data URI: must contain ';base64,', got: {location[:100]}"
            raise ValueError(msg)

        _, b64_data = location.split(";base64,", 1)
        decoded = base64.b64decode(b64_data)
        return len(decoded)
