import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypedDict

import httpx

logger = logging.getLogger("griptape_nodes")


class CreateSignedUploadUrlResponse(TypedDict):
    """Response type for create_signed_upload_url method."""

    url: str
    headers: dict
    method: str


class BaseStorageDriver(ABC):
    """Base class for storage drivers."""

    def __init__(self, workspace_directory: Path) -> None:
        """Initialize the storage driver with a workspace directory.

        Args:
            workspace_directory: The base workspace directory path.
        """
        self.workspace_directory = workspace_directory

    @abstractmethod
    def create_signed_upload_url(self, path: Path) -> CreateSignedUploadUrlResponse:
        """Create a signed upload URL for the given path.

        Args:
            path: The path of the file to create a signed URL for.

        Returns:
            CreateSignedUploadUrlResponse: A dictionary containing the signed URL, headers, and operation type.
        """
        ...

    @abstractmethod
    def create_signed_download_url(self, path: Path) -> str:
        """Create a signed download URL for the given path.

        Args:
            path: The path of the file to create a signed URL for.

        Returns:
            str: The signed URL for downloading the file.
        """
        ...

    @abstractmethod
    def delete_file(self, path: Path) -> None:
        """Delete a file from storage.

        Args:
            path: The path of the file to delete.
        """
        ...

    @abstractmethod
    def list_files(self) -> list[str]:
        """List all files in storage.

        Returns:
            A list of file names in storage.
        """
        ...

    def upload_file(self, path: Path, file_content: bytes) -> str:
        """Upload a file to storage.

        Args:
            path: The path of the file to upload.
            file_content: The file content as bytes.

        Returns:
            The URL where the file can be accessed.

        Raises:
            RuntimeError: If file upload fails.
        """
        try:
            # Get signed upload URL
            upload_response = self.create_signed_upload_url(path)

            # Upload the file using the signed URL
            response = httpx.request(
                upload_response["method"],
                upload_response["url"],
                content=file_content,
                headers=upload_response["headers"],
            )
            response.raise_for_status()

            # Return the download URL
            return self.create_signed_download_url(path)
        except httpx.HTTPStatusError as e:
            msg = f"Failed to upload file {path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Unexpected error uploading file {path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

    def download_file(self, path: Path) -> bytes:
        """Download a file from storage.

        Args:
            path: The path of the file to download.

        Returns:
            The file content as bytes.

        Raises:
            RuntimeError: If file download fails.
        """
        try:
            # Get signed download URL
            download_url = self.create_signed_download_url(path)

            # Download the file
            response = httpx.get(download_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to download file {path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Unexpected error downloading file {path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e
        else:
            return response.content
