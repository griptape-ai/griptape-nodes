from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode, NodeDependencies
from griptape_nodes.retained_mode.events.resource_events import (
    GetResourceInstanceStatusRequest,
    GetResourceInstanceStatusResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.resource_types.joke_resource import JokeInstance


class ModifyJokeNode(ControlNode):
    """Node that modifies a Joke resource instance.

    This node demonstrates how to modify the state of resource instances,
    showing that changes persist in the resource and can be accessed by
    other nodes holding the same resource handle.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="joke_resource_id",
                type="str",
                output_type="str",
                tooltip="The resource instance ID (handle) for the Joke to modify",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="new_lead_up",
                type="str",
                tooltip="New lead-up text (leave empty to keep current)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="new_punchline",
                type="str",
                tooltip="New punchline text (leave empty to keep current)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="resource_object_contents",
                type="str",
                output_type="str",
                tooltip="The complete updated joke text",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True},
            )
        )

    def process(self) -> None:
        instance_id = self.get_parameter_value("joke_resource_id")
        new_lead_up = self.get_parameter_value("new_lead_up")
        new_punchline = self.get_parameter_value("new_punchline")

        if not instance_id:
            msg = "No joke_resource_id provided"
            raise ValueError(msg)

        # Get the resource instance status to verify it exists
        request = GetResourceInstanceStatusRequest(instance_id=instance_id)
        result = GriptapeNodes.handle_request(request)

        if not isinstance(result, GetResourceInstanceStatusResultSuccess):
            msg = f"Failed to get Joke resource: {result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        # Access the ResourceInstance directly from the ResourceManager
        resource_manager = GriptapeNodes.ResourceManager()
        instance = resource_manager._instances.get(instance_id)

        if not isinstance(instance, JokeInstance):
            msg = f"Resource {instance_id} is not a JokeInstance"
            raise TypeError(msg)

        # Get the Joke object and modify it
        joke = instance.get_joke()

        if new_lead_up:
            joke.update_lead_up(new_lead_up)

        if new_punchline:
            joke.update_punchline(new_punchline)

        # Output the updated joke
        updated_joke = joke.get_full_joke()
        self.parameter_output_values["joke_resource_id"] = instance_id
        self.parameter_output_values["resource_object_contents"] = updated_joke

    def get_node_dependencies(self) -> NodeDependencies | None:
        """Declare that this node depends on a Joke resource instance."""
        instance_id = self.get_parameter_value("joke_resource_id")
        if instance_id:
            return NodeDependencies(resource_instances={instance_id})
        return None
