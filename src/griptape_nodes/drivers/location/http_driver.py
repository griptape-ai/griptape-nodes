"""Driver for HTTP/HTTPS URL locations."""

import httpx

from griptape_nodes.drivers.location.base_location_driver import BaseLocationDriver


class HttpDriver(BaseLocationDriver):
    """Driver for HTTP/HTTPS URL locations.

    Handles locations starting with "http://" or "https://" prefix,
    downloading content via async HTTP requests.
    """

    def can_handle(self, location: str) -> bool:
        """Check if location is an HTTP/HTTPS URL.

        Args:
            location: Location string to check

        Returns:
            True if location starts with "http://" or "https://", False otherwise
        """
        return location.startswith(("http://", "https://"))

    async def aload(self, location: str, timeout: float = 120.0) -> bytes:  # noqa: ASYNC109
        """Download file from HTTP/HTTPS URL.

        Args:
            location: HTTP/HTTPS URL to download from
            timeout: Timeout in seconds for HTTP request (default: 120.0)

        Returns:
            Downloaded bytes

        Raises:
            RuntimeError: If download fails or HTTP error occurs
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(location, timeout=timeout)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as e:
            error_msg = f"Failed to download from {location}: {e}"
            raise RuntimeError(error_msg) from e

    async def asave(self, location: str, data: bytes, existing_file_policy: str) -> str:
        """HTTP URLs are read-only, saving is not supported.

        Args:
            location: HTTP/HTTPS URL
            data: File content as bytes
            existing_file_policy: How to handle existing files (ignored)

        Raises:
            NotImplementedError: HTTP URLs are read-only for arbitrary URLs
        """
        error_msg = "Cannot save to arbitrary HTTP URL - use a specific storage driver instead"
        raise NotImplementedError(error_msg)
