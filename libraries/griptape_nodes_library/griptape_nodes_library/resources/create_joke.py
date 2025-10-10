from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.events.resource_events import (
    CreateResourceInstanceRequest,
    CreateResourceInstanceResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class CreateJokeNode(ControlNode):
    """Node that creates a Joke resource instance.

    This node demonstrates how to create resource instances that wrap
    complex objects that cannot be serialized with pickle/deepcopy.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="lead_up",
                default_value="Why did the chicken cross the road?",
                type="str",
                tooltip="The lead-up or setup of the joke",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="punchline",
                default_value="To get to the other side!",
                type="str",
                tooltip="The punchline of the joke",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="joke_resource_id",
                type="str",
                output_type="str",
                tooltip="The resource instance ID (handle) for the created Joke",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        lead_up = self.get_parameter_value("lead_up")
        punchline = self.get_parameter_value("punchline")

        # Create a Joke resource instance via the ResourceManager
        request = CreateResourceInstanceRequest(
            resource_type_name="JokeResourceType",
            capabilities={
                "lead_up": lead_up,
                "punchline": punchline,
            },
        )

        result = GriptapeNodes.handle_request(request)

        if isinstance(result, CreateResourceInstanceResultSuccess):
            # Store the resource instance ID (handle) as output
            instance_id = result.instance_id
            self.parameter_output_values["joke_resource_id"] = instance_id
        else:
            msg = f"Failed to create Joke resource: {result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004
