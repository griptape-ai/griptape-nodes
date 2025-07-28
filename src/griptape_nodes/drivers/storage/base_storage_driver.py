import logging
from abc import ABC, abstractmethod
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
        """
        ...

    @abstractmethod
    def list_files(self) -> list[str]:
        """List all files in storage.

        Returns:
            A list of file names in storage.
        """
        ...

    def upload_file(self, file_name: str, file_content: bytes) -> str:
        """Upload a file to storage.

        Args:
            file_name: The name of the file to upload.
            file_content: The file content as bytes.

        Returns:
            The URL where the file can be accessed.

        Raises:
            RuntimeError: If file upload fails.
        """
        try:
            # Get signed upload URL
            upload_response = self.create_signed_upload_url(file_name)

            # Upload the file using the signed URL
            response = httpx.request(
                upload_response["method"],
                upload_response["url"],
                content=file_content,
                headers=upload_response["headers"],
            )
            response.raise_for_status()

            # Return the download URL
            return self.create_signed_download_url(file_name)
        except httpx.HTTPStatusError as e:
            msg = f"Failed to upload file {file_name}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Unexpected error uploading file {file_name}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

    def download_file(self, file_name: str) -> bytes:
        """Download a file from the bucket.

        Args:
            file_name: The name of the file to download.

        Returns:
            The file content as bytes.

        Raises:
            RuntimeError: If file download fails.
        """
        try:
            # Get signed download URL
            download_url = self.create_signed_download_url(file_name)

            # Download the file
            response = httpx.get(download_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to download file {file_name}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Unexpected error downloading file {file_name}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e
        else:
            return response.content
