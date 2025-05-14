from typing import ClassVar

from griptape.mixins.singleton_mixin import SingletonMixin
from typing_extensions import TypeVar

from griptape_nodes.retained_mode.events.base_events import Payload

T = TypeVar("T", bound=Payload, default=Payload)


class PayloadRegistry(SingletonMixin):
    """Registry for payload types."""

    _registry: ClassVar[dict[str, type[Payload]]] = {}

    @classmethod
    def register(cls, payload_class: type[T]) -> type[T]:
        """Register a payload type.

        Args:
            payload_class: The payload class to register

        Returns:
            The registered class (for decorator use)
        """
        # Ensure we have an instance
        instance = cls()
        instance._registry[payload_class.__name__] = payload_class
        return payload_class

    @classmethod
    def get_type(cls, type_name: str) -> type[Payload] | None:
        """Get a payload type by name.

        Args:
            type_name: Name of the payload type

        Returns:
            The payload class or None if not found
        """
        # Ensure we have an instance
        instance = cls()
        return instance._registry.get(type_name)

    @classmethod
    def get_registry(cls) -> dict:
        """Get the full registry.

        Returns:
            Dictionary of payload type name to payload class
        """
        # Ensure we have an instance
        instance = cls()
        return instance._registry.copy()

    # Register decorator as a classmethod
    @classmethod
    def register_payload(cls, payload_class: type[T]) -> type[T]:
        """Decorator to register a payload type."""
        return cls.register(payload_class)
