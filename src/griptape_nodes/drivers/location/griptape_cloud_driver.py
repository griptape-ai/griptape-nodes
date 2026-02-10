"""Driver for Griptape Cloud asset locations."""

from urllib.parse import urljoin

import httpx

from griptape_nodes.drivers.location.base_location_driver import BaseLocationDriver
from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy


class GriptapeCloudDriver(BaseLocationDriver):
    """Driver for Griptape Cloud asset locations.

    Handles locations matching: https://cloud.griptape.ai/buckets/{id}/assets/{path}
    Supports both reading and writing via signed URLs.
    """

    def __init__(self, bucket_id: str, api_key: str, base_url: str = "https://cloud.griptape.ai") -> None:
        """Initialize GriptapeCloudDriver.

        Args:
            bucket_id: Griptape Cloud bucket ID
            api_key: API key for authentication
            base_url: Base URL for Griptape Cloud API (default: https://cloud.griptape.ai)
        """
        self.bucket_id = bucket_id
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def can_handle(self, location: str) -> bool:
        """Check if location is a Griptape Cloud asset URL.

        Args:
            location: Location string to check

        Returns:
            True if location is a cloud asset URL, False otherwise
        """
        return GriptapeCloudStorageDriver.is_cloud_asset_url(location, self.base_url)

    async def aload(self, location: str, timeout: float = 120.0) -> bytes:  # noqa: ASYNC109
        """Download file from Griptape Cloud storage.

        Args:
            location: Cloud asset URL
            timeout: Timeout in seconds for HTTP request (default: 120.0)

        Returns:
            Downloaded bytes

        Raises:
            RuntimeError: If download fails or URL conversion fails
        """
        workspace_path = GriptapeCloudStorageDriver.extract_workspace_path_from_cloud_url(location)

        if not workspace_path:
            error_msg = f"Failed to extract workspace path from cloud URL: {location}"
            raise RuntimeError(error_msg)

        api_url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/asset-urls/{workspace_path}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(api_url, json={"method": "GET"}, headers=self.headers, timeout=timeout)
                response.raise_for_status()
                signed_url = response.json()["url"]

                download_response = await client.get(signed_url, timeout=timeout)
                download_response.raise_for_status()
                return download_response.content

        except httpx.HTTPError as e:
            error_msg = f"Failed to download from cloud storage at {location}: {e}"
            raise RuntimeError(error_msg) from e

    async def asave(self, location: str, data: bytes, existing_file_policy: str) -> str:
        """Upload file to Griptape Cloud storage.

        Args:
            location: Cloud asset URL (determines save path)
            data: File content as bytes
            existing_file_policy: How to handle existing files (OVERWRITE, CREATE_NEW, FAIL)

        Returns:
            Permanent asset URL for accessing the saved file

        Raises:
            RuntimeError: If upload fails or URL parsing fails
        """
        policy = ExistingFilePolicy(existing_file_policy)

        if policy != ExistingFilePolicy.OVERWRITE:
            error_msg = f"Griptape Cloud storage only supports OVERWRITE policy, got {policy.value}"
            raise RuntimeError(error_msg)

        workspace_path = GriptapeCloudStorageDriver.extract_workspace_path_from_cloud_url(location)

        if not workspace_path:
            error_msg = f"Failed to extract workspace path from cloud URL: {location}"
            raise RuntimeError(error_msg)

        try:
            async with httpx.AsyncClient() as client:
                # Create asset
                asset_url = urljoin(self.base_url, f"/api/buckets/{self.bucket_id}/assets")
                asset_response = await client.put(
                    asset_url,
                    json={"name": workspace_path},
                    headers=self.headers,
                )
                asset_response.raise_for_status()

                # Get signed upload URL
                upload_url_endpoint = urljoin(
                    self.base_url, f"/api/buckets/{self.bucket_id}/asset-urls/{workspace_path}"
                )
                upload_response = await client.post(
                    upload_url_endpoint,
                    json={"operation": "PUT"},
                    headers=self.headers,
                )
                upload_response.raise_for_status()
                upload_url = upload_response.json()["url"]

                # Upload data
                put_response = await client.put(upload_url, content=data)
                put_response.raise_for_status()

                # Return permanent asset URL
                return urljoin(self.base_url, f"/buckets/{self.bucket_id}/assets/{workspace_path}")

        except httpx.HTTPError as e:
            error_msg = f"Failed to upload to cloud storage at {location}: {e}"
            raise RuntimeError(error_msg) from e
