import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from griptape_nodes.retained_mode.managers.resource_components.capability_field import (
    CapabilityField,
    validate_capabilities,
)
from griptape_nodes.retained_mode.managers.resource_components.resource_instance import ResourceInstance
from griptape_nodes.retained_mode.managers.resource_components.resource_type import ResourceType

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.resource_components.resource_instance import Requirements

logger = logging.getLogger("griptape_nodes")


class ComputeBackend(StrEnum):
    """Supported compute backends."""

    CPU = "cpu"
    CUDA = "cuda"  # NVIDIA GPU
    MPS = "mps"  # Apple Metal Performance Shaders


# Compute capability field names
ComputeCapability = Literal[
    "compute",  # List of available compute backends: ["cpu", "cuda", "mps"]
]


class ComputeInstance(ResourceInstance):
    """Resource instance representing available compute backends."""

    def can_be_freed(self) -> bool:
        """Compute resources can be freed when no longer needed."""
        return True

    def free(self) -> None:
        """Free compute resource instance."""
        logger.debug("Freeing compute resource instance %s", self.get_instance_id())

    def get_capability_typed(self, key: ComputeCapability) -> Any:
        """Type-safe capability getter using Literal types."""
        return self.get_capability_value(key)


class ComputeResourceType(ResourceType):
    """Resource type for compute backend availability."""

    def get_capability_schema(self) -> list[CapabilityField]:
        """Get the capability schema for compute resources."""
        return [
            CapabilityField(
                name="compute",
                type_hint=list,
                description="List of available compute backends: 'cpu', 'cuda', 'mps'",
                required=True,
            ),
        ]

    def create_instance(self, capabilities: dict[str, Any]) -> ResourceInstance:
        """Create a new compute resource instance."""
        # Validate capabilities against schema
        validation_errors = validate_capabilities(self.get_capability_schema(), capabilities)
        if validation_errors:
            error_msg = f"Invalid compute capabilities: {', '.join(validation_errors)}"
            raise ValueError(error_msg)

        return ComputeInstance(resource_type=self, instance_id_prefix="compute", capabilities=capabilities)

    def select_best_compatible_instance(
        self, compatible_instances: list[ResourceInstance], _requirements: "Requirements | None" = None
    ) -> ResourceInstance | None:
        """Select the best compute instance from compatible ones.

        Returns the first compatible instance (no special selection criteria).
        """
        if not compatible_instances:
            return None

        return compatible_instances[0]
