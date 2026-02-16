"""File driver for raw base64-encoded strings."""

import base64
import re

from griptape_nodes.file.base_file_driver import BaseFileDriver

# Base64 alphabet: A-Z, a-z, 0-9, +, /, and = for padding.
# We also allow whitespace which base64.b64decode tolerates.
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/\s]+=*$")

# Minimum length to consider a string as raw base64.
# Short strings are more likely to be filenames or other identifiers.
_MIN_BASE64_LENGTH = 20


class Base64FileDriver(BaseFileDriver):
    """Fallback driver that decodes raw base64-encoded strings.

    Handles strings that are not valid URIs or file paths but are valid
    base64-encoded data.  Registered at priority 90 so it is checked after
    all protocol-specific drivers but before LocalFileDriver (100).
    """

    @property
    def priority(self) -> int:
        """Return priority 90 — just before LocalFileDriver (100).

        Returns:
            Priority value of 90
        """
        return 90

    def can_handle(self, location: str) -> bool:
        """Check if location looks like raw base64.

        Rejects anything that already has a recognized URI scheme or
        contains path separators, then attempts a trial decode.

        Args:
            location: Location string to check

        Returns:
            True if the string is decodable base64 data
        """
        if len(location) < _MIN_BASE64_LENGTH:
            return False

        # Skip anything that looks like a URI or file path
        if location.startswith(("data:", "http://", "https://", "file://", "/", ".")):
            return False
        if "/" in location and not location.endswith("="):
            # Slash is valid base64, but a string like "some/path.txt" is a path.
            # Heuristic: if it contains '/' but does NOT end with '=' padding,
            # it's more likely a path than base64.
            return False

        if not _BASE64_RE.match(location):
            return False

        try:
            base64.b64decode(location, validate=True)
        except Exception:
            return False

        return True

    async def read(self, location: str, timeout: float) -> bytes:  # noqa: ARG002, ASYNC109
        """Decode raw base64 string to bytes.

        Args:
            location: Raw base64-encoded string
            timeout: Ignored (no network operation)

        Returns:
            Decoded bytes

        Raises:
            ValueError: If base64 decoding fails
        """
        try:
            return base64.b64decode(location, validate=True)
        except Exception as e:
            msg = f"Failed to decode raw base64 data: {e}"
            raise ValueError(msg) from e

    async def exists(self, location: str) -> bool:
        """Raw base64 "exists" if it can be decoded.

        Args:
            location: Raw base64-encoded string

        Returns:
            True if the base64 string can be decoded
        """
        try:
            base64.b64decode(location, validate=True)
        except Exception:
            return False
        return True

    def get_size(self, location: str) -> int:
        """Get decoded size of raw base64 data.

        Args:
            location: Raw base64-encoded string

        Returns:
            Size in bytes of the decoded data

        Raises:
            ValueError: If base64 decoding fails
        """
        try:
            return len(base64.b64decode(location, validate=True))
        except Exception as e:
            msg = f"Failed to decode raw base64 data: {e}"
            raise ValueError(msg) from e
