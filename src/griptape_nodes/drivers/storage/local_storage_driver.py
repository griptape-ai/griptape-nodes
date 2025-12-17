import logging
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx

from griptape_nodes.drivers.storage.base_storage_driver import BaseStorageDriver, CreateSignedUploadUrlResponse
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy, WriteFileRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils import resolve_workspace_path

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
            # Default to localhost - the storage driver creator can pass a proxy URL if needed
            self.base_url = f"http://{STATIC_SERVER_HOST}:{STATIC_SERVER_PORT}{STATIC_SERVER_URL}"
        else:
            self.base_url = base_url

    def create_signed_upload_url(
        self, path: Path, existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE
    ) -> CreateSignedUploadUrlResponse:
        # on_write_file_request seems to work most reliably with an absolute path.
        absolute_path = resolve_workspace_path(path, self.workspace_directory)

        # Always delegate to OSManager for file path resolution and policy handling.
        # Creating an empty file before the upload url gives us a chance to claim ownership
        # of that particular file when creating the upload url. The file policy is not
        # checked when actually uploading the file, it will always overwrite.
        os_manager = GriptapeNodes.OSManager()
        write_request = WriteFileRequest(
            file_path=str(absolute_path),
            content=b"",  # Empty content for URL generation
            existing_file_policy=existing_file_policy,
        )
        result = os_manager.on_write_file_request(write_request)

        if not result.succeeded():
            msg = f"WriteFileRequest failed: {result.result_details}"
            raise FileExistsError(msg)

        # Use the resolved filename from OSManager
        # Type checker: result is WriteFileResultSuccess when succeeded() is True
        resolved_path = Path(result.final_file_path)  # type: ignore[attr-defined]

        # WriteFileRequest always returns an absolute path, but the url needs
        # to be workspace relative if passed in path was workspace relative.
        if not path.is_absolute():
            resolved_path = resolved_path.relative_to(self.workspace_directory)

        static_url = urljoin(self.base_url, "/static-upload-urls")
        try:
            response = httpx.post(static_url, json={"file_path": str(resolved_path)})
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to create upload URL for file {resolved_path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()
        url = response_data.get("url")
        if url is None:
            msg = f"Failed to get upload URL for file {resolved_path}: {response_data}"
            logger.error(msg)
            raise ValueError(msg)

        return {
            "url": url,
            "headers": response_data.get("headers", {}),
            "method": "PUT",
            "file_path": str(resolved_path),
        }

    def save_file(
        self, path: Path, file_content: bytes, existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE
    ) -> str:
        """Save a file to local storage by writing directly to disk.

        Args:
            path: The path of the file to save.
            file_content: The file content as bytes.
            existing_file_policy: How to handle existing files. Defaults to OVERWRITE.

        Returns:
            The absolute file path where the file was saved.

        Raises:
            FileExistsError: When existing_file_policy is FAIL and file already exists.
            RuntimeError: If file write fails.
        """
        # Resolve to absolute if relative
        absolute_path = resolve_workspace_path(path, self.workspace_directory)

        # Write file using OSManager with policy handling
        os_manager = GriptapeNodes.OSManager()
        write_request = WriteFileRequest(
            file_path=str(absolute_path),
            content=file_content,
            existing_file_policy=existing_file_policy,
        )
        result = os_manager.on_write_file_request(write_request)

        # Check failure cases first
        if not result.succeeded():
            details = str(result.result_details)
            if "already exists" in details:
                raise FileExistsError(details)
            msg = f"Failed to write file {path}: {details}"
            raise RuntimeError(msg)

        # Success path: return the resolved absolute file path
        # Type checker: result is WriteFileResultSuccess when succeeded() is True
        return result.final_file_path  # type: ignore[attr-defined]

    def create_signed_download_url(self, path: Path) -> str:
        # Resolve path, treating relative paths as workspace-relative
        absolute_path = resolve_workspace_path(path, self.workspace_directory)

        # Automatically determine if the file is external to the workspace
        try:
            workspace_relative_path = absolute_path.relative_to(self.workspace_directory.resolve())
            # Internal files: use workspace-relative path
            url = f"{self.base_url}/{workspace_relative_path.as_posix()}"
        except ValueError:
            # For external files, use /external path and strip leading slash from absolute path
            path_str = str(absolute_path).removeprefix("/")
            # Build URL with /external prefix, replacing the /workspace part of base_url
            base_without_workspace = self.base_url.rsplit("/workspace", 1)[0]
            url = f"{base_without_workspace}/external/{path_str}"

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

    def get_asset_url(self, path: Path) -> str:
        """Get the permanent URL for a local asset.

        Returns the absolute file path.

        Args:
            path: The path of the file

        Returns:
            Absolute file path as a string
        """
        absolute_path = resolve_workspace_path(path, self.workspace_directory)
        return str(absolute_path)
