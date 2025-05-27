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
        bucket_id: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        headers: dict | None = None,
    ) -> None:
        """Initialize the GriptapeCloudStorageDriver.

        Args:
            bucket_id: The ID of the bucket to use. If not provided, a new bucket will be provisioned.
            base_url: The base URL for the Griptape Cloud API. If not provided, it will be retrieved from the environment variable "GT_CLOUD_BASE_URL" or default to "https://cloud.griptape.ai".
            api_key: The API key for authentication. If not provided, it will be retrieved from the environment variable "GT_CLOUD_API_KEY".
            headers: Additional headers to include in the requests. If not provided, the default headers will be used.
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

    def create_signed_upload_url(self, file_name: str) -> CreateSignedUploadUrlResponse:
        self._create_asset(file_name)

        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/asset-urls/{file_name}")
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
        url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/asset-urls/{file_name}")
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
