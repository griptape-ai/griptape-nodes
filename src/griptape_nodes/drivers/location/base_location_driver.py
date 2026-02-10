"""Base class for file location loading drivers."""

from abc import ABC, abstractmethod

from asyncio_thread_runner import ThreadRunner


class BaseLocationDriver(ABC):
    """Base class for file location loading drivers.

    Each driver handles a specific location type (data URIs, HTTP URLs, file paths, etc.).
    Drivers are registered with LocationDriverRegistry and selected based on location format.
    """

    @abstractmethod
    def can_handle(self, location: str) -> bool:
        """Check if this driver can handle the given location.

        Args:
            location: Location string to check

        Returns:
            True if this driver can handle the location, False otherwise
        """
        ...

    @abstractmethod
    async def aload(self, location: str, timeout: float = 120.0) -> bytes:  # noqa: ASYNC109
        """Load file data from location asynchronously.

        Args:
            location: Location string to load from
            timeout: Timeout in seconds for network operations (default: 120.0)

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If resource does not exist
            ValueError: If location format is invalid
            RuntimeError: If load operation fails
        """
        ...

    def load(self, location: str, timeout: float = 120.0) -> bytes:
        """Load file data from location synchronously.

        Default implementation calls aload() via ThreadRunner.
        Override if a more efficient synchronous implementation exists.

        Args:
            location: Location string to load from
            timeout: Timeout in seconds for network operations (default: 120.0)

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If resource does not exist
            ValueError: If location format is invalid
            RuntimeError: If load operation fails
        """
        with ThreadRunner() as runner:
            return runner.run(self.aload(location, timeout))

    @abstractmethod
    async def asave(self, location: str, data: bytes, existing_file_policy: str) -> str:
        """Save file data to location asynchronously.

        Args:
            location: Location string to save to
            data: File content as bytes
            existing_file_policy: How to handle existing files (OVERWRITE, CREATE_NEW, FAIL)

        Returns:
            URL for accessing the saved file (for UI display)

        Raises:
            FileExistsError: If file exists and policy is FAIL
            NotImplementedError: If this driver does not support saving
            RuntimeError: If save operation fails
        """
        ...

    def save(self, location: str, data: bytes, existing_file_policy: str) -> str:
        """Save file data to location synchronously.

        Default implementation calls asave() via ThreadRunner.
        Override if a more efficient synchronous implementation exists.

        Args:
            location: Location string to save to
            data: File content as bytes
            existing_file_policy: How to handle existing files (OVERWRITE, CREATE_NEW, FAIL)

        Returns:
            URL for accessing the saved file (for UI display)

        Raises:
            FileExistsError: If file exists and policy is FAIL
            NotImplementedError: If this driver does not support saving
            RuntimeError: If save operation fails
        """
        with ThreadRunner() as runner:
            return runner.run(self.asave(location, data, existing_file_policy))
