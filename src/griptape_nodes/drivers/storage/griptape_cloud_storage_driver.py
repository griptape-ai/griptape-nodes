import logging
import os
from urllib.parse import urljoin

import httpx

from griptape_nodes.drivers.storage.base_storage_driver import BaseStorageDriver, CreateSignedUploadUrlResponse

logger = logging.getLogger("griptape_nodes")


class GriptapeCloudStorageDriver(BaseStorageDriver):
    """Stores files using the Griptape Cloud's Asset APIs."""

    def __init__(
        self,
        *,
        bucket_id: str,
        base_url: str | None = None,
        api_key: str | None = None,
        headers: dict | None = None,
        static_files_directory: str | None = None,
    ) -> None:
        """Initialize the GriptapeCloudStorageDriver.

        Args:
            bucket_id: The ID of the bucket to use. Required.
            base_url: The base URL for the Griptape Cloud API. If not provided, it will be retrieved from the environment variable "GT_CLOUD_BASE_URL" or default to "https://cloud.griptape.ai".
            api_key: The API key for authentication. If not provided, it will be retrieved from the environment variable "GT_CLOUD_API_KEY".
            headers: Additional headers to include in the requests. If not provided, the default headers will be used.
            static_files_directory: The directory path prefix for static files. If provided, file names will be prefixed with this path.
        """
        self.base_url = (
            base_url if base_url is not None else os.environ.get("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        )
        self.api_key = api_key if api_key is not None else os.environ.get("GT_CLOUD_API_KEY")
        self.headers = (
            headers
            if headers is not None
            else {
                "Authorization": f"Bearer {self.api_key}",
            }
        )

        self.bucket_id = bucket_id
        self.static_files_directory = static_files_directory

    def _get_full_file_path(self, file_name: str) -> str:
        """Get the full file path including the static files directory prefix.

        Args:
            file_name: The base file name.

        Returns:
            The full file path with static files directory prefix if configured.
        """
        if self.static_files_directory:
            return f"{self.static_files_directory}/{file_name}"
        return file_name

    def create_signed_upload_url(self, file_name: str) -> CreateSignedUploadUrlResponse:
        full_file_path = self._get_full_file_path(file_name)
        self._create_asset(full_file_path)

        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/asset-urls/{full_file_path}")
        try:
            response = httpx.post(url, json={"operation": "PUT"}, headers=self.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to create presigned URL for file {file_name}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()

        return {"url": response_data["url"], "headers": response_data.get("headers", {}), "method": "PUT"}

    def create_signed_download_url(self, file_name: str) -> str:
        full_file_path = self._get_full_file_path(file_name)
        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/asset-urls/{full_file_path}")
        try:
            response = httpx.post(url, json={"method": "GET"}, headers=self.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to create presigned URL for file {file_name}: {e}"
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
            response = httpx.get(url, headers=self.headers, params={"prefix": self.static_files_directory or ""})
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
            if self.static_files_directory and name.startswith(f"{self.static_files_directory}/"):
                name = name[len(f"{self.static_files_directory}/") :]
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

    def delete_file(self, file_name: str) -> None:
        """Delete a file from the bucket.

        Args:
            file_name: The name of the file to delete.
        """
        full_file_path = self._get_full_file_path(file_name)
        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/assets/{full_file_path}")

        try:
            response = httpx.delete(url, headers=self.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to delete file {file_name}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e
