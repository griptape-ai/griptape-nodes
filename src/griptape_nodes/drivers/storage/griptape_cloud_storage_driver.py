import logging
import os
from pathlib import Path
from urllib.parse import urljoin

import httpx

from griptape_nodes.drivers.storage.base_storage_driver import BaseStorageDriver, CreateSignedUploadUrlResponse

logger = logging.getLogger("griptape_nodes")


class GriptapeCloudStorageDriver(BaseStorageDriver):
    """Stores files using the Griptape Cloud's Asset APIs."""

    def __init__(
        self,
        workspace_directory: Path,
        *,
        bucket_id: str,
        api_key: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize the GriptapeCloudStorageDriver.

        Args:
            workspace_directory: The base workspace directory path.
            bucket_id: The ID of the bucket to use. Required.
            api_key: The API key for authentication. If not provided, it will be retrieved from the environment variable "GT_CLOUD_API_KEY".
            static_files_directory: The directory path prefix for static files. If provided, file names will be prefixed with this path.
            **kwargs: Additional keyword arguments including base_url and headers.
        """
        super().__init__(workspace_directory)

        self.base_url = kwargs.get("base_url") or os.environ.get("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        self.api_key = api_key if api_key is not None else os.environ.get("GT_CLOUD_API_KEY")
        self.headers = kwargs.get("headers") or {"Authorization": f"Bearer {self.api_key}"}

        self.bucket_id = bucket_id

    def create_signed_upload_url(self, path: Path) -> CreateSignedUploadUrlResponse:
        self._create_asset(path.as_posix())

        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/asset-urls/{path.as_posix()}")
        try:
            response = httpx.post(url, json={"operation": "PUT"}, headers=self.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to create presigned upload URL for file {path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()

        return {"url": response_data["url"], "headers": response_data.get("headers", {}), "method": "PUT"}

    def create_signed_download_url(self, path: Path) -> str:
        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/asset-urls/{path.as_posix()}")
        try:
            response = httpx.post(url, json={"method": "GET"}, headers=self.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to create presigned download URL for file {path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()

        return response_data["url"]

    def _create_asset(self, asset_name: str) -> str:
        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/assets")
        try:
            response = httpx.put(url=url, json={"name": asset_name}, headers=self.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = str(e)
            logger.error(msg)
            raise ValueError(msg) from e

        return response.json()["name"]

    @staticmethod
    def create_bucket(bucket_name: str, *, base_url: str, api_key: str) -> str:
        """Create a new bucket in Griptape Cloud.

        Args:
            bucket_name: Name for the bucket.
            base_url: The base URL for the Griptape Cloud API.
            api_key: The API key for authentication.

        Returns:
            The bucket ID of the created bucket.

        Raises:
            RuntimeError: If bucket creation fails.
        """
        headers = {"Authorization": f"Bearer {api_key}"}
        url = urljoin(base_url, "/api/buckets")
        payload = {"name": bucket_name}

        try:
            response = httpx.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to create bucket '{bucket_name}': {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()
        bucket_id = response_data["bucket_id"]

        logger.info("Created new Griptape Cloud bucket '%s' with ID: %s", bucket_name, bucket_id)
        return bucket_id

    def list_files(self) -> list[str]:
        """List all files in storage.

        Returns:
            A list of file names in storage.

        Raises:
            RuntimeError: If file listing fails.
        """
        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/assets")
        try:
            response = httpx.get(url, headers=self.headers, params={"prefix": self.workspace_directory.name or ""})
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to list files in bucket {self.bucket_id}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()
        assets = response_data.get("assets", [])

        file_names = []
        for asset in assets:
            name = asset.get("name", "")
            # Remove the static files directory prefix if it exists
            if self.workspace_directory and name.startswith(f"{self.workspace_directory.name}/"):
                name = name[len(f"{self.workspace_directory.name}/") :]
            file_names.append(name)

        return file_names

    @staticmethod
    def list_buckets(*, base_url: str, api_key: str) -> list[dict]:
        """List all buckets in Griptape Cloud.

        Args:
            base_url: The base URL for the Griptape Cloud API.
            api_key: The API key for authentication.

        Returns:
            A list of dictionaries containing bucket information.
        """
        headers = {"Authorization": f"Bearer {api_key}"}
        url = urljoin(base_url, "/api/buckets")

        try:
            response = httpx.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to list buckets: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        return response.json().get("buckets", [])

    def delete_file(self, path: Path) -> None:
        """Delete a file from the bucket.

        Args:
            path: The path of the file to delete.
        """
        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/assets/{path.as_posix()}")

        try:
            response = httpx.delete(url, headers=self.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to delete file {path}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e
