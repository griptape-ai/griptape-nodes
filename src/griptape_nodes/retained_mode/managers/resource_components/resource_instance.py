import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from griptape_nodes.retained_mode.managers.resource_components.comparator import Comparator

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.resource_components.resource_type import ResourceType

logger = logging.getLogger("griptape_nodes")


class ResourceInstance(ABC):
    """Base class for resource instances that can be locked and managed."""

    def __init__(self, resource_type: "ResourceType", instance_id_prefix: str, capabilities: dict[str, Any]):
        self._resource_type = resource_type
        self._capabilities = deepcopy(capabilities)
        self._instance_id = f"{instance_id_prefix}_{uuid4().hex}"
        self._locked_by = None

    def get_resource_type(self) -> "ResourceType":
        """Get the resource type of this instance."""
        return self._resource_type

    def get_capabilities(self) -> dict[str, Any]:
        """Get all capabilities of this resource."""
        return self._capabilities

    def has_capability(self, key: str) -> bool:
        """Check if resource has a specific capability key."""
        return key in self._capabilities

    def get_capability(self, key: str) -> Any:
        """Get a specific capability value."""
        return self._capabilities[key]

    def get_instance_id(self) -> str:
        """Unique handle/ID for this instance."""
        return self._instance_id

    def acquire_lock(self, owner_id: str) -> bool:
        """Try to acquire exclusive lock."""
        if self._locked_by is None:
            self._locked_by = owner_id
            logger.debug("Resource %s locked by %s", self._instance_id, owner_id)
            return True
        return False

    def release_lock(self, owner_id: str) -> bool:
        """Release lock if owned by owner_id."""
        if self._locked_by == owner_id:
            self._locked_by = None
            logger.debug("Resource %s unlocked by %s", self._instance_id, owner_id)
            return True
        return False

    def is_locked(self) -> bool:
        """Check if resource is currently locked."""
        return self._locked_by is not None

    def is_locked_by(self, owner_id: str) -> bool:
        """Check if resource is locked by specific owner."""
        return self._locked_by == owner_id

    def get_lock_owner(self) -> str | None:
        """Get the current lock owner, if any."""
        return self._locked_by

    def is_compatible_with(self, requirements: dict[str, Any] | None) -> bool:
        """Check if this instance can satisfy the requirements."""
        if requirements is None:
            return True

        for key, req_spec in requirements.items():
            # Handle both tuple and non-tuple formats
            if isinstance(req_spec, tuple):
                required_value, comparator_str = req_spec
            else:
                required_value, comparator_str = req_spec, Comparator.EQUALS

            # Convert string to StrEnum
            comparator = Comparator(comparator_str)

            if not self._compare_values(key, required_value, comparator):
                return False
        return True

    def _compare_values(self, key: str, required: Any, comparator: Comparator) -> bool:
        """Compare actual capability value against required value using comparator."""
        match comparator:
            case Comparator.NOT_PRESENT:
                return key not in self._capabilities
            case _:
                # For all other comparators, key must exist
                if key not in self._capabilities:
                    return False
                actual = self._capabilities[key]
                return self._apply_comparator(actual, required, comparator, key)

    def _apply_comparator(self, actual: Any, required: Any, comparator: Comparator, key: str) -> bool:
        """Apply the comparator operation."""
        match comparator:
            case Comparator.EQUALS:
                return actual == required
            case Comparator.NOT_EQUALS:
                return actual != required
            case (
                Comparator.GREATER_THAN_OR_EQUAL
                | Comparator.GREATER_THAN
                | Comparator.LESS_THAN_OR_EQUAL
                | Comparator.LESS_THAN
            ):
                return self._apply_numeric_comparator(actual, required, comparator)
            case Comparator.STARTS_WITH | Comparator.INCLUDES:
                return self._apply_string_comparator(actual, required, comparator)
            case Comparator.HAS_ANY | Comparator.HAS_ALL:
                return self._apply_container_comparator(actual, required, comparator, key)
            case Comparator.CUSTOM:
                return self._resource_type.handle_custom_requirement(
                    _instance=self,
                    _key=key,
                    _requirement_value=required,
                    _actual_value=actual,
                    _capabilities=self._capabilities,
                )
            case _:
                msg = f"Unknown comparator: {comparator}"
                raise ValueError(msg)

    def _apply_numeric_comparator(self, actual: Any, required: Any, comparator: Comparator) -> bool:
        """Apply numeric comparison operators."""
        match comparator:
            case Comparator.GREATER_THAN_OR_EQUAL:
                return actual >= required
            case Comparator.GREATER_THAN:
                return actual > required
            case Comparator.LESS_THAN_OR_EQUAL:
                return actual <= required
            case Comparator.LESS_THAN:
                return actual < required
            case _:
                msg = f"Invalid numeric comparator: {comparator}"
                raise ValueError(msg)

    def _apply_string_comparator(self, actual: Any, required: Any, comparator: Comparator) -> bool:
        """Apply string comparison operators."""
        match comparator:
            case Comparator.STARTS_WITH:
                return str(actual).startswith(str(required))
            case Comparator.INCLUDES:
                return str(required) in str(actual)
            case _:
                msg = f"Invalid string comparator: {comparator}"
                raise ValueError(msg)

    def _apply_container_comparator(self, actual: Any, required: Any, comparator: Comparator, key: str) -> bool:
        """Apply container comparison operators."""
        if not hasattr(actual, "__iter__") or isinstance(actual, str):
            msg = f"{comparator} comparator requires capability '{key}' to be a container, got {type(actual)}"
            raise ValueError(msg)
        if not hasattr(required, "__iter__") or isinstance(required, str):
            msg = f"{comparator} comparator requires requirement value to be a container, got {type(required)}"
            raise ValueError(msg)

        match comparator:
            case Comparator.HAS_ANY:
                return any(item in actual for item in required)
            case Comparator.HAS_ALL:
                return all(item in actual for item in required)
            case _:
                msg = f"Invalid container comparator: {comparator}"
                raise ValueError(msg)

    @abstractmethod
    def can_be_reclaimed(self) -> bool:
        """Check if this resource can be safely destroyed."""

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up/destroy this resource instance."""
