from abc import ABC, abstractmethod
from typing import TypedDict


class CreateSignedUploadUrlResponse(TypedDict):
    """Response type for create_signed_upload_url method."""

    url: str
    headers: dict
    method: str


class BaseStorageDriver(ABC):
    """Base class for storage drivers."""

    @abstractmethod
    def create_signed_upload_url(self, file_name: str) -> CreateSignedUploadUrlResponse:
        """Create a signed upload URL for the given file name.

        Args:
            file_name: The name of the file to create a signed URL for.

        Returns:
            CreateSignedUploadUrlResponse: A dictionary containing the signed URL, headers, and operation type.
        """
        ...

    @abstractmethod
    def create_signed_download_url(self, file_name: str) -> str:
        """Create a signed download URL for the given file name.

        Args:
            file_name: The name of the file to create a signed URL for.

        Returns:
            str: The signed URL for downloading the file.
        """
        ...

    @abstractmethod
    def delete_file(self, file_name: str) -> None:
        """Delete a file from storage.

        Args:
            file_name: The name of the file to delete.

        Raises:
            ValueError: If the file could not be deleted.
        """
        ...

    @abstractmethod
    def list_files(self) -> list[str]:
        """List all files available in storage.

        Returns:
            List of file names available in storage.
        """
        ...
