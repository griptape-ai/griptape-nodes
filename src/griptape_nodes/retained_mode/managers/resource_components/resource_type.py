from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.resource_components.capability_field import CapabilityField
    from griptape_nodes.retained_mode.managers.resource_components.resource_instance import (
        Requirements,
        ResourceInstance,
    )


class ResourceType(ABC):
    """Base class for resource type handlers."""

    @abstractmethod
    def get_capability_schema(self) -> list["CapabilityField"]:
        """Get the capability schema for this resource type."""

    @abstractmethod
    def create_instance(self, capabilities: dict[str, Any]) -> "ResourceInstance":
        """Create a resource instance with the specified capabilities."""

    def select_best_compatible_instance(
        self, compatible_instances: list["ResourceInstance"], _requirements: "Requirements | None" = None
    ) -> "ResourceInstance | None":
        """Select the best instance from pre-filtered compatible instances.

        Args:
            compatible_instances: List of instances that are already known to be compatible
            _requirements: The original requirements dict for context

        Returns:
            The best instance to use, or None if none are suitable

        Note:
            All instances in compatible_instances are guaranteed to satisfy the requirements.
            This method allows ResourceType implementations to apply their own selection
            logic (e.g., prefer instances with more resources, least used, etc.).
        """
        # Default behavior: return the first compatible instance if available
        # Implementors can override this method to provide more optimized instance selection
        return compatible_instances[0] if compatible_instances else None

    def handle_custom_requirement(
        self,
        *,
        _instance: "ResourceInstance",
        _key: str,
        _requirement_value: Any,
        _actual_value: Any,
        _capabilities: dict[str, Any],
    ) -> bool:
        """Handle custom requirement logic with full context.

        This method is called when a requirement uses the Comparator.CUSTOM comparator,
        allowing ResourceType implementations to define complex comparison logic that
        goes beyond the standard built-in comparators.

        Use cases for custom comparators:
        - Complex mathematical relationships (e.g., GPU memory + system memory > threshold)
        - Version compatibility checks (e.g., CUDA version compatibility matrices)
        - Hardware compatibility logic (e.g., CPU instruction set compatibility)
        - Multi-field validation (e.g., ensuring RAM and CPU are balanced)

        Args:
            _instance: The resource instance being evaluated
            _key: The requirement key being evaluated
            _requirement_value: The value from the requirements dict
            _actual_value: The actual capability value
            _capabilities: Full capabilities dict for context

        Returns:
            True if the custom requirement is satisfied, False otherwise

        Raises:
            NotImplementedError: If the ResourceType doesn't implement custom logic
        """
        msg = f"Custom requirement handling not implemented for {type(self).__name__}"
        raise NotImplementedError(msg)

    def supports_serialization(self) -> bool:
        """Check if this resource type supports serialization/deserialization.

        Resource types that manage complex objects with state that needs to be
        persisted across workflow save/load cycles should return True and implement
        the serialization methods below.

        Examples of serializable resources:
        - Business objects with saveable state (e.g., Joke with lead_up/punchline)
        - Configured pipelines or models with parameters
        - Complex data structures that can be reconstructed

        Examples of non-serializable resources:
        - System resources (CPU, GPU, memory)
        - Active connections (network, database)
        - Resources tied to the current process/machine

        Returns:
            True if this resource type supports serialization, False otherwise
        """
        return False

    def serialize_instance_to_recipe(self, _instance: "ResourceInstance") -> dict[str, Any]:
        """Serialize a resource instance to a recipe dictionary.

        The recipe should contain all information needed to recreate the resource
        in its current state. This typically includes the resource type name and
        the current values of all capabilities.

        This method is only called if supports_serialization() returns True.

        Args:
            _instance: The resource instance to serialize

        Returns:
            A dictionary containing the resource type name and all state needed
            to recreate the instance

        Raises:
            NotImplementedError: If serialization is not supported (default behavior)
            TypeError: If the instance is not of the expected type
        """
        msg = f"Serialization not implemented for {type(self).__name__}"
        raise NotImplementedError(msg)

    def deserialize_instance_from_recipe(self, _recipe: dict[str, Any]) -> "ResourceInstance":
        """Deserialize a resource instance from a recipe dictionary.

        Creates a new resource instance with the same state as the original,
        based on the information in the recipe.

        This method is only called if supports_serialization() returns True.

        Args:
            _recipe: The recipe dictionary containing resource type name and state

        Returns:
            A newly created resource instance with the same state as the original

        Raises:
            NotImplementedError: If deserialization is not supported (default behavior)
            ValueError: If the recipe is invalid or incomplete
        """
        msg = f"Deserialization not implemented for {type(self).__name__}"
        raise NotImplementedError(msg)
