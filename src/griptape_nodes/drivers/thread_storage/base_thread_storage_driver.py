"""Base thread storage driver abstract class."""

from abc import ABC, abstractmethod

from griptape.drivers.memory.conversation import BaseConversationMemoryDriver

from griptape_nodes.retained_mode.events.agent_events import ThreadMetadata
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager


class BaseThreadStorageDriver(ABC):
    """Abstract base class for thread storage backends."""

    def __init__(self, config_manager: ConfigManager, secrets_manager: SecretsManager) -> None:
        """Initialize the thread storage driver.

        Args:
            config_manager: Configuration manager instance
            secrets_manager: Secrets manager instance
        """
        self.config_manager = config_manager
        self.secrets_manager = secrets_manager

    @abstractmethod
    def create_thread(self, title: str | None = None, local_id: str | None = None) -> tuple[str, dict]:
        """Create a new thread with metadata.

        Args:
            title: Optional thread title
            local_id: Optional client-side identifier

        Returns:
            Tuple of (thread_id, metadata_dict)
        """
        ...

    @abstractmethod
    def get_thread_metadata(self, thread_id: str) -> dict:
        """Get metadata for a thread.

        Args:
            thread_id: The thread identifier

        Returns:
            Metadata dictionary
        """
        ...

    @abstractmethod
    def update_thread_metadata(self, thread_id: str, **updates) -> dict:
        """Update thread metadata.

        Args:
            thread_id: The thread identifier
            **updates: Key-value pairs to update in metadata

        Returns:
            Updated metadata dictionary
        """
        ...

    @abstractmethod
    def list_threads(self) -> list[ThreadMetadata]:
        """List all threads with metadata.

        Returns:
            List of ThreadMetadata objects
        """
        ...

    @abstractmethod
    def delete_thread(self, thread_id: str) -> None:
        """Delete a thread.

        Args:
            thread_id: The thread identifier

        Raises:
            ValueError: If thread is not archived or doesn't exist
        """
        ...

    @abstractmethod
    def thread_exists(self, thread_id: str) -> bool:
        """Check if a thread exists.

        Args:
            thread_id: The thread identifier

        Returns:
            True if thread exists, False otherwise
        """
        ...

    @abstractmethod
    def get_conversation_memory_driver(self, thread_id: str | None) -> BaseConversationMemoryDriver:
        """Get the appropriate conversation memory driver for this thread.

        Args:
            thread_id: The thread identifier (can be None for GTC backend)

        Returns:
            Conversation memory driver instance
        """
        ...
