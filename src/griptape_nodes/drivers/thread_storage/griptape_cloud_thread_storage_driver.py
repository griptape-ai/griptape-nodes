"""Griptape Cloud thread storage driver."""

import logging
import os
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx
from griptape.drivers.memory.conversation import BaseConversationMemoryDriver
from griptape.drivers.memory.conversation.griptape_cloud import GriptapeCloudConversationMemoryDriver

from griptape_nodes.drivers.thread_storage.base_thread_storage_driver import BaseThreadStorageDriver
from griptape_nodes.retained_mode.events.agent_events import ThreadMetadata

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
HTTP_NOT_FOUND = 404
logger = logging.getLogger("griptape_nodes")


class GriptapeCloudThreadStorageDriver(BaseThreadStorageDriver):
    """Griptape Cloud implementation of thread storage."""

    @property
    def base_url(self) -> str:
        """Get the base URL for Griptape Cloud API."""
        return os.environ.get("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")

    @property
    def _headers(self) -> dict:
        """Get the authorization headers for API requests."""
        api_key = self.secrets_manager.get_secret(API_KEY_ENV_VAR)
        if not api_key:
            msg = f"Secret '{API_KEY_ENV_VAR}' not found for Griptape Cloud thread storage"
            raise ValueError(msg)
        return {"Authorization": f"Bearer {api_key}"}

    def _get_url(self, path: str) -> str:
        """Construct full API URL from path."""
        return urljoin(self.base_url, path)

    def create_thread(self, title: str | None = None, local_id: str | None = None) -> tuple[str, dict]:
        url = self._get_url("/api/threads")

        now = datetime.now(UTC).isoformat()

        # Build metadata for the request
        metadata = {
            "created_at": now,
            "updated_at": now,
        }
        if local_id is not None:
            metadata["local_id"] = local_id

        # Build request body
        request_body: dict[str, str | dict] = {"metadata": metadata}
        if title is not None:
            request_body["name"] = title

        try:
            response = httpx.post(url, json=request_body, headers=self._headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to create thread in Griptape Cloud: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()
        thread_id = response_data["thread_id"]

        # Build metadata dict to return (matching local driver behavior)
        result_metadata = response_data.get("metadata", {})
        if title is not None:
            result_metadata["title"] = title

        return thread_id, result_metadata

    def get_thread_metadata(self, thread_id: str) -> dict:
        url = self._get_url(f"/api/threads/{thread_id}")

        try:
            response = httpx.get(url, headers=self._headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == HTTP_NOT_FOUND:
                return {}
            msg = f"Failed to get thread {thread_id} from Griptape Cloud: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()

        # Extract metadata from response
        metadata = response_data.get("metadata", {})

        # Map GTC's "name" field to our "title" field for consistency
        if response_data.get("name"):
            metadata["title"] = response_data["name"]

        return metadata

    def update_thread_metadata(self, thread_id: str, **updates) -> dict:
        # First, get current metadata
        current_metadata = self.get_thread_metadata(thread_id)

        now = datetime.now(UTC).isoformat()

        # Merge updates into current metadata
        for key, value in updates.items():
            if value is not None:
                current_metadata[key] = value

        current_metadata["updated_at"] = now

        if "created_at" not in current_metadata:
            current_metadata["created_at"] = now

        url = self._get_url(f"/api/threads/{thread_id}")

        # Build request body
        request_body: dict[str, str | dict] = {"metadata": current_metadata}

        # If title was updated, also set the name field
        if "title" in updates and updates["title"] is not None:
            request_body["name"] = updates["title"]

        try:
            response = httpx.patch(url, json=request_body, headers=self._headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to update thread {thread_id} in Griptape Cloud: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()

        # Return updated metadata
        result_metadata = response_data.get("metadata", {})
        if response_data.get("name"):
            result_metadata["title"] = response_data["name"]

        return result_metadata

    def list_threads(self) -> list[ThreadMetadata]:
        url = self._get_url("/api/threads")

        try:
            response = httpx.get(url, headers=self._headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to list threads from Griptape Cloud: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        response_data = response.json()
        threads_data = response_data.get("threads", [])

        threads = []
        for thread_data in threads_data:
            thread_id = thread_data.get("thread_id")
            if not thread_id:
                continue

            metadata = thread_data.get("metadata", {})

            thread_metadata = ThreadMetadata(
                thread_id=thread_id,
                title=thread_data.get("name"),
                created_at=metadata.get("created_at"),
                updated_at=metadata.get("updated_at"),
                message_count=thread_data.get("message_count", 0),
                archived=metadata.get("archived", False),
                local_id=metadata.get("local_id"),
            )
            threads.append(thread_metadata)

        # Sort by updated_at descending (most recent first)
        threads.sort(key=lambda t: t.updated_at or "", reverse=True)

        return threads

    def delete_thread(self, thread_id: str) -> None:
        if not self.thread_exists(thread_id):
            msg = f"Thread {thread_id} not found"
            raise ValueError(msg)

        meta = self.get_thread_metadata(thread_id)
        if not meta.get("archived", False):
            msg = f"Cannot delete thread {thread_id}. Archive it first."
            raise ValueError(msg)

        url = self._get_url(f"/api/threads/{thread_id}")

        try:
            response = httpx.delete(url, headers=self._headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = f"Failed to delete thread {thread_id} from Griptape Cloud: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

    def thread_exists(self, thread_id: str) -> bool:
        try:
            meta = self.get_thread_metadata(thread_id)
            return bool(meta)
        except Exception:
            return False

    def get_conversation_memory_driver(self, thread_id: str | None) -> BaseConversationMemoryDriver:
        api_key = self.secrets_manager.get_secret(API_KEY_ENV_VAR)
        if not api_key:
            msg = f"Secret '{API_KEY_ENV_VAR}' not found for Griptape Cloud thread storage"
            raise ValueError(msg)
        return GriptapeCloudConversationMemoryDriver(api_key=api_key, thread_id=thread_id)
