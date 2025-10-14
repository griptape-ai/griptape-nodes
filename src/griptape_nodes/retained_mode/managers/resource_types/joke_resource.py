import logging
import threading
from typing import Any, Literal

from griptape_nodes.retained_mode.managers.resource_components.capability_field import (
    CapabilityField,
    validate_capabilities,
)
from griptape_nodes.retained_mode.managers.resource_components.resource_instance import ResourceInstance
from griptape_nodes.retained_mode.managers.resource_components.resource_type import ResourceType

logger = logging.getLogger("griptape_nodes")


# Joke capability field names
JokeCapability = Literal[
    "lead_up",
    "punchline",
]


class Joke:
    """A simple joke class that deliberately breaks serialization.

    This class is designed to test the resource serialization architecture
    by holding state that cannot be pickled or deepcopied.
    """

    def __init__(self, lead_up: str, punchline: str):
        self.lead_up = lead_up
        self.punchline = punchline
        # Add a thread lock to make this object unpicklable
        # Locks cannot be pickled, which simulates complex objects with active state
        self._lock = threading.Lock()
        # Also add a lambda to further ensure it can't be pickled
        self._unpicklable_function = lambda: f"{self.lead_up} {self.punchline}"

    def get_full_joke(self) -> str:
        """Get the complete joke as a single string."""
        with self._lock:
            return self._unpicklable_function()

    def update_lead_up(self, new_lead_up: str) -> None:
        """Update the lead-up portion of the joke."""
        with self._lock:
            self.lead_up = new_lead_up
            # Recreate the lambda with new values
            self._unpicklable_function = lambda: f"{self.lead_up} {self.punchline}"

    def update_punchline(self, new_punchline: str) -> None:
        """Update the punchline portion of the joke."""
        with self._lock:
            self.punchline = new_punchline
            # Recreate the lambda with new values
            self._unpicklable_function = lambda: f"{self.lead_up} {self.punchline}"

    def __getstate__(self) -> None:
        """Prevent pickling by raising an exception."""
        msg = "Joke objects cannot be pickled - they contain unpicklable thread locks and lambdas"
        raise TypeError(msg)

    def __deepcopy__(self, memo: dict) -> None:
        """Prevent deepcopy by raising an exception."""
        msg = "Joke objects cannot be deepcopied - they contain unpicklable thread locks and lambdas"
        raise TypeError(msg)


class JokeInstance(ResourceInstance):
    """Resource instance representing a Joke object.

    This wraps a Joke and provides access to it through the resource manager.
    Nodes hold handles (instance IDs) to JokeInstance objects rather than
    direct references to Joke objects.
    """

    def __init__(self, resource_type: "ResourceType", capabilities: dict[str, Any]):
        # Don't call super().__init__ yet because it tries to deepcopy capabilities
        # and we need to create the Joke object first
        self._resource_type = resource_type
        self._instance_id = f"joke_{self._generate_unique_id()}"
        self._locked_by = None

        # Store the original capability values (without deepcopy)
        self._capabilities = capabilities

        # Create the actual Joke object from capabilities
        lead_up = capabilities.get("lead_up", "")
        punchline = capabilities.get("punchline", "")
        self._joke: Joke | None = Joke(lead_up, punchline)

    def _generate_unique_id(self) -> str:
        """Generate a unique ID for this instance."""
        from uuid import uuid4

        return str(uuid4())

    def get_joke(self) -> Joke:
        """Get the actual Joke object.

        This is the interface nodes use to access the joke.
        """
        if self._joke is None:
            msg = "Joke instance has been freed and is no longer available"
            raise RuntimeError(msg)
        return self._joke

    def get_capability_value(self, key: str) -> Any:
        """Get a specific capability value.

        For joke instances, we return live values from the joke object
        rather than cached values, since the joke can be modified.
        """
        if self._joke is None:
            return self._capabilities.get(key)

        match key:
            case "lead_up":
                return self._joke.lead_up
            case "punchline":
                return self._joke.punchline
            case _:
                return self._capabilities.get(key)

    def can_be_freed(self) -> bool:
        """Joke resources can be freed when not in use."""
        return True

    def free(self) -> None:
        """Free this joke resource instance."""
        logger.debug("Freeing Joke resource instance %s", self._instance_id)
        # Clean up the joke object
        self._joke = None


class JokeResourceType(ResourceType):
    """Resource type for Joke objects.

    This manages the creation and lifecycle of Joke resource instances.
    """

    def get_capability_schema(self) -> list[CapabilityField]:
        """Get the capability schema for Joke resources."""
        return [
            CapabilityField(
                name="lead_up",
                type_hint=str,
                description="The lead-up or setup of the joke",
                required=True,
            ),
            CapabilityField(
                name="punchline",
                type_hint=str,
                description="The punchline of the joke",
                required=True,
            ),
        ]

    def create_instance(self, capabilities: dict[str, Any]) -> ResourceInstance:
        """Create a new Joke resource instance."""
        # Validate capabilities against schema
        validation_errors = validate_capabilities(self.get_capability_schema(), capabilities)
        if validation_errors:
            error_msg = f"Invalid Joke capabilities: {', '.join(validation_errors)}"
            raise ValueError(error_msg)

        return JokeInstance(resource_type=self, capabilities=capabilities)

    def supports_serialization(self) -> bool:
        """Joke resources support serialization.

        Even though the underlying Joke object cannot be pickled,
        we can serialize it by extracting the lead_up and punchline.
        """
        return True

    def serialize_instance_to_recipe(self, instance: ResourceInstance) -> dict[str, Any]:
        """Serialize a Joke instance to a recipe dict.

        The recipe contains all the information needed to recreate
        the joke in its current state.
        """
        if not isinstance(instance, JokeInstance):
            msg = f"Cannot serialize non-JokeInstance: {type(instance)}"
            raise TypeError(msg)

        joke = instance.get_joke()
        recipe = {
            "resource_type_name": type(self).__name__,
            "capabilities": {
                "lead_up": joke.lead_up,
                "punchline": joke.punchline,
            },
        }
        return recipe

    def deserialize_instance_from_recipe(self, recipe: dict[str, Any]) -> ResourceInstance:
        """Deserialize a Joke instance from a recipe dict.

        Creates a new JokeInstance with the same state as the original.
        """
        if recipe.get("resource_type_name") != type(self).__name__:
            msg = (
                f"Recipe resource type mismatch: expected {type(self).__name__}, got {recipe.get('resource_type_name')}"
            )
            raise ValueError(msg)

        capabilities = recipe.get("capabilities")
        if not capabilities:
            msg = "Recipe missing capabilities"
            raise ValueError(msg)

        return self.create_instance(capabilities)
