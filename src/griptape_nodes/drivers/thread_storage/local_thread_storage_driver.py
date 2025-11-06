"""Local filesystem thread storage driver."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from griptape.drivers.memory.conversation import BaseConversationMemoryDriver
from griptape.drivers.memory.conversation.local import LocalConversationMemoryDriver
from griptape.memory.structure import ConversationMemory

from griptape_nodes.drivers.thread_storage.base_thread_storage_driver import BaseThreadStorageDriver
from griptape_nodes.retained_mode.events.agent_events import ThreadMetadata
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager


class LocalThreadStorageDriver(BaseThreadStorageDriver):
    """Local filesystem implementation of thread storage."""

    def __init__(self, threads_directory: Path, config_manager: ConfigManager, secrets_manager: SecretsManager) -> None:
        """Initialize the local thread storage driver.

        Args:
            threads_directory: Directory for storing thread data
            config_manager: Configuration manager instance
            secrets_manager: Secrets manager instance
        """
        super().__init__(config_manager, secrets_manager)
        self.threads_directory = threads_directory

    def create_thread(self, title: str | None = None, local_id: str | None = None) -> tuple[str, dict]:
        thread_id = str(uuid.uuid4())

        conversation_memory = self._get_or_create_conversation_memory(thread_id)

        now = datetime.now(UTC).isoformat()
        conversation_memory.meta = {
            "created_at": now,
            "updated_at": now,
        }

        if title is not None:
            conversation_memory.meta["title"] = title
        if local_id is not None:
            conversation_memory.meta["local_id"] = local_id

        conversation_memory.conversation_memory_driver.store(conversation_memory.runs, conversation_memory.meta)

        return thread_id, conversation_memory.meta

    def get_thread_metadata(self, thread_id: str) -> dict:
        conversation_memory = self._get_or_create_conversation_memory(thread_id)
        if conversation_memory.meta is None:
            return {}
        return conversation_memory.meta

    def update_thread_metadata(self, thread_id: str, **updates) -> dict:
        conversation_memory = self._get_or_create_conversation_memory(thread_id)
        now = datetime.now(UTC).isoformat()

        if conversation_memory.meta is None:
            conversation_memory.meta = {}

        for key, value in updates.items():
            if value is not None:
                conversation_memory.meta[key] = value

        conversation_memory.meta["updated_at"] = now

        if "created_at" not in conversation_memory.meta:
            conversation_memory.meta["created_at"] = now

        conversation_memory.conversation_memory_driver.store(conversation_memory.runs, conversation_memory.meta)

        return conversation_memory.meta

    def list_threads(self) -> list[ThreadMetadata]:
        threads = []

        if not self.threads_directory.exists():
            return threads

        thread_ids = [
            thread_file.stem.replace("thread_", "") for thread_file in self.threads_directory.glob("thread_*.json")
        ]

        for thread_id in thread_ids:
            meta = self.get_thread_metadata(thread_id)
            conversation_memory = self._get_or_create_conversation_memory(thread_id)
            message_count = len(conversation_memory.runs)

            threads.append(
                ThreadMetadata(
                    thread_id=thread_id,
                    title=meta.get("title"),
                    created_at=meta.get("created_at", ""),
                    updated_at=meta.get("updated_at", ""),
                    message_count=message_count,
                    archived=meta.get("archived", False),
                    local_id=meta.get("local_id"),
                )
            )

        threads.sort(key=lambda t: t.updated_at, reverse=True)

        return threads

    def delete_thread(self, thread_id: str) -> None:
        thread_file = self.threads_directory / f"thread_{thread_id}.json"

        if not thread_file.exists():
            msg = f"Thread {thread_id} not found"
            raise ValueError(msg)

        meta = self.get_thread_metadata(thread_id)
        if not meta.get("archived", False):
            msg = f"Cannot delete thread {thread_id}. Archive it first."
            raise ValueError(msg)

        thread_file.unlink()

    def thread_exists(self, thread_id: str) -> bool:
        thread_file = self.threads_directory / f"thread_{thread_id}.json"
        return thread_file.exists()

    def get_conversation_memory_driver(self, thread_id: str | None) -> BaseConversationMemoryDriver:
        if thread_id is None:
            msg = "thread_id is required for local storage backend"
            raise ValueError(msg)

        thread_file = self.threads_directory / f"thread_{thread_id}.json"
        return LocalConversationMemoryDriver(persist_file=str(thread_file))

    def _get_or_create_conversation_memory(self, thread_id: str) -> ConversationMemory:
        """Get or create ConversationMemory instance for a thread."""
        driver = self.get_conversation_memory_driver(thread_id)
        return ConversationMemory(conversation_memory_driver=driver)
