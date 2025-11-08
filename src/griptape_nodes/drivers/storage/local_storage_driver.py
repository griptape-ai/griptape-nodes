import logging
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx

from griptape_nodes.drivers.storage.base_storage_driver import BaseStorageDriver, CreateSignedUploadUrlResponse

logger = logging.getLogger("griptape_nodes")


class LocalStorageDriver(BaseStorageDriver):
    """Stores files using the engine's local static server."""

    def __init__(self, workspace_directory: Path, base_url: str | None = None) -> None:
        """Initialize the LocalStorageDriver.

        Args:
            workspace_directory: The base workspace directory path.
            base_url: The base URL for the static file server. If not provided, it will be constructed
        """
        super().__init__(workspace_directory)

        from griptape_nodes.servers.static import (
            STATIC_SERVER_ENABLED,
            STATIC_SERVER_HOST,
            STATIC_SERVER_PORT,
            STATIC_SERVER_URL,
        )

        if not STATIC_SERVER_ENABLED:
            msg = "Static server is not enabled. Please set STATIC_SERVER_ENABLED to True."
            raise ValueError(msg)
        if base_url is None:
            self.base_url = f"http://{STATIC_SERVER_HOST}:{STATIC_SERVER_PORT}{STATIC_SERVER_URL}"
        else:
            self.base_url = base_url

    def create_signed_upload_url(self, path: Path) -> CreateSignedUploadUrlResponse:
        static_url = urljoin(self.base_url, "/static-upload-urls")
        try:
            response = httpx.post(static_url, json={"file_path": str(path)})
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to create upload URL for file {path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()
        url = response_data.get("url")
        if url is None:
            msg = f"Failed to get upload URL for file {path}: {response_data}"
            logger.error(msg)
            raise ValueError(msg)

        return {"url": url, "headers": response_data.get("headers", {}), "method": "PUT"}

    def create_signed_download_url(self, path: Path) -> str:
        # The base_url already includes the /static path, so just append the path
        url = f"{self.base_url}/{path.as_posix()}"
        # Add a cache-busting query parameter to the URL so that the browser always reloads the file
        cache_busted_url = f"{url}?t={int(time.time())}"
        return cache_busted_url

    def delete_file(self, path: Path) -> None:
        """Delete a file from local storage.

        Args:
            path: The path of the file to delete.
        """
        # Use the static server's delete endpoint
        delete_url = urljoin(self.base_url, f"/static-files/{path.as_posix()}")

        try:
            response = httpx.delete(delete_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to delete file {path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

    def list_files(self) -> list[str]:
        """List all files in local storage.

        Returns:
            A list of file names in storage.
        """
        # Use the static server's list endpoint
        list_url = urljoin(self.base_url, "/static-uploads/")

        try:
            response = httpx.get(list_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to list files: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()
        return response_data.get("files", [])
