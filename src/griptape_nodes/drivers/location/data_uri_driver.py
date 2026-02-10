"""Driver for data URI locations (data:image/png;base64,...)."""

import base64

from griptape_nodes.drivers.location.base_location_driver import BaseLocationDriver


class DataUriDriver(BaseLocationDriver):
    """Driver for data URI locations.

    Handles locations starting with "data:" prefix, decoding base64-encoded data.
    Example: "data:image/png;base64,iVBORw0KGgo..."
    """

    def can_handle(self, location: str) -> bool:
        """Check if location is a data URI.

        Args:
            location: Location string to check

        Returns:
            True if location starts with "data:", False otherwise
        """
        return location.startswith("data:")

    async def aload(self, location: str, timeout: float = 120.0) -> bytes:  # noqa: ASYNC109, ARG002
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
            error_msg = f"Invalid data URI: must start with 'data:', got: {location[:50]}"
            raise ValueError(error_msg)

        if ";base64," not in location:
            error_msg = f"Invalid data URI: must contain ';base64,', got: {location[:100]}"
            raise ValueError(error_msg)

        _, b64_data = location.split(";base64,", 1)

        try:
            return base64.b64decode(b64_data)
        except Exception as e:
            error_msg = f"Failed to decode base64 data from data URI: {e}"
            raise ValueError(error_msg) from e

    async def asave(self, location: str, data: bytes, existing_file_policy: str) -> str:
        """Data URIs are read-only, saving is not supported.

        Args:
            location: Data URI string
            data: File content as bytes
            existing_file_policy: How to handle existing files (ignored)

        Raises:
            NotImplementedError: Data URIs are read-only
        """
        error_msg = "Cannot save to data URI - data URIs are read-only"
        raise NotImplementedError(error_msg)
