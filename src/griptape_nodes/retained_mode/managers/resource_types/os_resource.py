import logging
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


# OS capability field names
OSCapability = Literal[
    "platform",
    "arch",
    "version",
]


class OSInstance(ResourceInstance):
    """Resource instance representing an operating system environment."""

    def can_be_freed(self) -> bool:
        """OS resources can be freed when no longer needed."""
        return True

    def free(self) -> None:
        """Free OS resource instance."""
        logger.debug("Freeing OS resource instance %s", self.get_instance_id())

    def get_capability_typed(self, key: OSCapability) -> Any:
        """Type-safe capability getter using Literal types."""
        return self.get_capability_value(key)


class OSResourceType(ResourceType):
    """Resource type for operating system environments."""

    def get_capability_schema(self) -> list[CapabilityField]:
        """Get the capability schema for OS resources."""
        return [
            CapabilityField(
                name="platform",
                type_hint=str,
                description="Operating system platform: 'linux', 'darwin', 'windows'",
                required=True,
            ),
            CapabilityField(
                name="arch",
                type_hint=str,
                description="System architecture: 'x86_64', 'arm64', 'aarch64'",
                required=True,
            ),
            CapabilityField(
                name="version",
                type_hint=str,
                description="Operating system version string",
                required=False,
            ),
        ]

    def create_instance(self, capabilities: dict[str, Any]) -> ResourceInstance:
        """Create a new OS resource instance."""
        # Validate capabilities against schema
        validation_errors = validate_capabilities(self.get_capability_schema(), capabilities)
        if validation_errors:
            error_msg = f"Invalid OS capabilities: {', '.join(validation_errors)}"
            raise ValueError(error_msg)

        return OSInstance(resource_type=self, instance_id_prefix="os", capabilities=capabilities)

    def select_best_compatible_instance(
        self, compatible_instances: list[ResourceInstance], _requirements: "Requirements | None" = None
    ) -> ResourceInstance | None:
        """Select the best OS instance from compatible ones.

        Returns the first compatible instance (no special selection criteria for now).
        """
        if not compatible_instances:
            return None

        return compatible_instances[0]
