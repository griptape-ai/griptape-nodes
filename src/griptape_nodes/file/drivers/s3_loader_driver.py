"""Loader driver for S3 bucket locations."""

from griptape_nodes.file.loader_driver import LoaderDriver


class S3LoaderDriver(LoaderDriver):
    """Read-only loader driver for S3 bucket locations.

    Handles locations with s3:// prefix.
    Requires boto3 to be installed.

    Note: This is a placeholder implementation. Full S3 support requires boto3.
    """

    def __init__(self) -> None:
        """Initialize S3LoaderDriver.

        Raises:
            ImportError: If boto3 is not available
        """
        try:
            import boto3  # noqa: F401
        except ImportError as e:
            msg = "S3LoaderDriver requires boto3. Install it with: pip install boto3"
            raise ImportError(msg) from e

    def can_handle(self, location: str) -> bool:
        """Check if location is an S3 URL.

        Args:
            location: Location string to check

        Returns:
            True if location starts with "s3://"
        """
        return location.startswith("s3://")

    async def read(self, location: str, timeout: float) -> bytes:
        """Download file from S3.

        Args:
            location: S3 URL (s3://bucket/key)
            timeout: Timeout in seconds (currently ignored)

        Returns:
            Downloaded bytes

        Raises:
            NotImplementedError: S3 support not yet implemented
        """
        msg = "S3LoaderDriver not yet implemented. Full S3 support coming soon."
        raise NotImplementedError(msg)

    async def exists(self, location: str) -> bool:
        """Check if S3 object exists.

        Args:
            location: S3 URL (s3://bucket/key)

        Returns:
            False (not yet implemented)
        """
        return False

    def get_size(self, location: str) -> int:
        """Get S3 object size.

        Args:
            location: S3 URL (s3://bucket/key)

        Returns:
            0 (not yet implemented)
        """
        return 0
