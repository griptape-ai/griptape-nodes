import logging
from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.resource_components.resource_instance import ResourceInstance
from griptape_nodes.retained_mode.managers.resource_components.resource_type import ResourceType

logger = logging.getLogger("griptape_nodes")


@dataclass
class ResourceStatus:
    resource_type: ResourceType
    instance_id: str
    owner_of_lock: str | None
    capabilities: dict[str, Any]

    def is_locked(self) -> bool:
        """Check if this resource is currently locked."""
        return self.owner_of_lock is not None


class ResourceManager:
    """Manager for resource allocation, locking, and lifecycle management."""

    def __init__(self, _event_manager: EventManager) -> None:
        self._resource_types: set[ResourceType] = set()
        # Maps instance_id to ResourceInstance objects
        self._instances: dict[str, ResourceInstance] = {}

        # Register event handlers when resource events are created

    def register_resource_type(self, resource_type: ResourceType) -> None:
        """Register a new resource type handler."""
        self._resource_types.add(resource_type)
        logger.debug("Registered resource type: %s", type(resource_type).__name__)

    def get_compatible_resource_instances(
        self, resource_type: ResourceType, requirements: dict[str, Any] | None = None, *, include_locked: bool = False
    ) -> list[ResourceInstance]:
        """Get list of resource instances that are compatible with the requirements.

        Args:
            resource_type: The type of resource to filter by
            requirements: Optional specific requirements to match. If None, returns all instances of the type.
            include_locked: If True, also include locked instances
        """
        compatible_instances = []

        for instance in self._instances.values():
            # Skip locked instances unless explicitly requested
            if instance.is_locked() and not include_locked:
                continue

            # Check if instance belongs to the specified resource type
            if instance.get_resource_type() != resource_type:
                continue

            # If no requirements specified, any instance of this type works
            if requirements is None:
                compatible_instances.append(instance)
                continue

            # Check if this instance is compatible with the requirements
            if instance.is_compatible_with(requirements):
                compatible_instances.append(instance)

        return compatible_instances

    def create_resource_instance(self, resource_type: ResourceType, capabilities: dict[str, Any]) -> str:
        """Create a new resource instance and add it to tracking.

        Args:
            resource_type: The resource type to create an instance of
            capabilities: Dict of capabilities for the new instance

        Returns:
            instance_id of the newly created instance

        Note:
            This method can raise exceptions from resource_type.create_instance().
            Caller is responsible for handling any creation failures.
        """
        new_instance = resource_type.create_instance(capabilities)
        self._instances[new_instance.get_instance_id()] = new_instance
        logger.debug("Created new resource instance %s", new_instance.get_instance_id())
        return new_instance.get_instance_id()

    def delete_resource_instance(self, instance_id: str, *, force_unlock: bool = False) -> None:
        """Delete a resource instance and remove it from tracking.

        Args:
            instance_id: The ID of the instance to delete
            force_unlock: If True, force unlock locked instances. If False, raise exception for locked instances.

        Raises:
            ValueError: If instance_id does not exist or if instance is locked and force_unlock=False

        Note:
            Any exceptions from cleanup() will also propagate to the caller.
        """
        instance = self._instances.get(instance_id)
        if instance is None:
            msg = f"Resource instance {instance_id} does not exist"
            raise ValueError(msg)

        # Check if locked and handle based on force_unlock
        if instance.is_locked():
            if not force_unlock:
                owner = instance.get_lock_owner()
                msg = f"Resource instance {instance_id} is locked by {owner}. Use force_unlock=True to override."
                raise ValueError(msg)

            owner = instance.get_lock_owner()
            instance._locked_by = None  # Force unlock
            logger.error("Force unlocked resource instance %s from owner %s during deletion", instance_id, owner)

        # Clean up the instance
        instance.cleanup()

        # Remove from tracking
        del self._instances[instance_id]
        logger.debug("Deleted resource instance %s", instance_id)

    def acquire_resource_instance_lock(
        self, owner_id: str, resource_type: ResourceType, requirements: dict[str, Any] | None = None
    ) -> str | None:
        """Try to acquire an existing resource instance, returns instance_id or None."""
        # Get compatible unlocked instances
        compatible_instances = self.get_compatible_resource_instances(resource_type, requirements, include_locked=False)

        # Let ResourceType select the best instance from compatible ones
        best_instance = resource_type.select_best_compatible_instance(compatible_instances, requirements)

        if best_instance:
            try:
                best_instance.acquire_lock(owner_id)
                logger.debug(
                    "Acquired existing resource instance %s for owner %s", best_instance.get_instance_id(), owner_id
                )
                return best_instance.get_instance_id()
            except ValueError as e:
                # Bail
                logger.error("Failed to acquire lock on selected instance: %s", e)
                return None

        req_name = str(requirements) if requirements else "any"
        logger.warning(
            "Could not acquire existing resource instance for requirements %s and owner %s", req_name, owner_id
        )
        return None

    def release_resource_instance_lock(self, instance_id: str, owner_id: str) -> None:
        """Release resource instance lock.

        Args:
            instance_id: The ID of the resource instance to release
            owner_id: The ID of the entity releasing the lock

        Raises:
            ValueError: If the instance does not exist or is not locked by the specified owner
        """
        instance = self._instances.get(instance_id)
        if instance is None:
            msg = f"Resource instance {instance_id} does not exist"
            raise ValueError(msg)

        instance.release_lock(owner_id)  # Will throw if this fails.
        logger.debug("Released resource instance %s from owner %s", instance_id, owner_id)

    def get_resource_instance_by_id(self, instance_id: str) -> ResourceInstance | None:
        """Get resource instance by its instance_id."""
        return self._instances.get(instance_id)

    def get_resource_instances(self) -> dict[str, ResourceInstance]:
        """Get all tracked resource instances."""
        return self._instances

    def get_resource_instance_status(self, instance_id: str) -> ResourceStatus | None:
        """Get status information for a resource instance."""
        instance = self._instances.get(instance_id)
        if instance is None:
            return None

        return ResourceStatus(
            resource_type=instance.get_resource_type(),
            instance_id=instance_id,
            owner_of_lock=instance.get_lock_owner(),
            capabilities=instance.get_capabilities(),
        )

    def get_registered_resource_types(self) -> set[ResourceType]:
        """Get all registered resource types."""
        return self._resource_types
