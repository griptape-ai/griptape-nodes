import logging
from typing import Literal

from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Resampling
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    CreateConnectionResultFailure,
    IncomingConnection,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
    OutgoingConnection,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
    SetParameterValueResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.options import Options
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("pillow_nodes_library")


class RescaleImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.migrate_message = ParameterMessage(
            variant="warning",
            full_width=True,
            button_text="Create RescaleImage Node",
            value="This node is being deprecated.\nPlease use the RescaleImage node from the Griptape Nodes Library.",
            traits={Button(label="Create RescaleImage Node", icon="plus", variant="secondary", on_click=self._migrate)},
        )
        self.add_node_element(self.migrate_message)

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="input_image",
            )
        )
        self.add_parameter(
            Parameter(
                name="scale",
                default_value=2.0,
                input_types=["float"],
                type="float",
                tooltip="scale",
            )
        )
        self.add_parameter(
            Parameter(
                name="resample_strategy",
                default_value="bicubic",
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=[
                            "nearest",
                            "box",
                            "bilinear",
                            "hamming",
                            "bicubic",
                            "lanczos",
                        ]
                    )
                },
                tooltip="resample_strategy",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageUrlArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _get_connections(self) -> tuple[list[IncomingConnection], list[OutgoingConnection]]:
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self.name))
        if not isinstance(result, ListConnectionsForNodeResultSuccess):
            logger.error("Failed to list connections for node '%s'", self.name)
            return [], []
        return result.incoming_connections, result.outgoing_connections

    def _connect_input(
        self,
        incoming_connections: list[IncomingConnection],
        new_node: str,
        current_parameter: str,
        new_node_parameter: str,
    ) -> bool:
        """Connect input parameters from the original connections to a new node."""
        for incoming_connection in incoming_connections:
            if incoming_connection.target_parameter_name == current_parameter:
                result = GriptapeNodes.handle_request(
                    CreateConnectionRequest(
                        source_node_name=incoming_connection.source_node_name,
                        source_parameter_name=incoming_connection.source_parameter_name,
                        target_node_name=new_node,
                        target_parameter_name=new_node_parameter,
                        initial_setup=True,
                    )
                )
                if isinstance(result, CreateConnectionResultFailure):
                    logger.error(
                        "Failed to create input connection from '%s.%s' to '%s.%s'",
                        incoming_connection.source_node_name,
                        incoming_connection.source_parameter_name,
                        new_node,
                        new_node_parameter,
                    )
                    logger.error(result)
                    return False
        return True

    def _connect_output(
        self,
        outgoing_connections: list[OutgoingConnection],
        new_node: str,
        current_parameter: str,
        new_node_parameter: str,
    ) -> bool:
        """Connect output parameters from a new node to the original connection targets."""
        for outgoing_connection in outgoing_connections:
            if outgoing_connection.source_parameter_name == current_parameter:
                result = GriptapeNodes.handle_request(
                    CreateConnectionRequest(
                        source_node_name=new_node,
                        source_parameter_name=new_node_parameter,
                        target_node_name=outgoing_connection.target_node_name,
                        target_parameter_name=outgoing_connection.target_parameter_name,
                        initial_setup=True,
                    )
                )
                if isinstance(result, CreateConnectionResultFailure):
                    logger.error(
                        "Failed to create output connection from '%s.%s' to '%s.%s'",
                        new_node,
                        new_node_parameter,
                        outgoing_connection.target_node_name,
                        outgoing_connection.target_parameter_name,
                    )
                    logger.error(result)
                    return False
        return True

    def _migrate(self, button: Button, button_details: ButtonDetailsMessagePayload) -> NodeMessageResult | None:  # noqa: ARG002
        # Create the new node
        new_node_name = f"{self.name}_migrated"

        new_node = self._create_new_node(
            node_library="Griptape Nodes Library",
            node_type="RescaleImage",
            node_name=new_node_name,
            position="top",
            offset=20,
        )

        # Create connections
        incoming_connections, outgoing_connections = self._get_connections()

        # Connect input parameters
        self._connect_input(
            incoming_connections=incoming_connections,
            new_node=new_node,
            current_parameter="input_image",
            new_node_parameter="input_image",
        )

        # Connect output parameters
        self._connect_output(
            outgoing_connections=outgoing_connections,
            new_node=new_node,
            current_parameter="output_image",
            new_node_parameter="output",
        )

        # Handle parameter migration

        # Scale
        scale_value = self.get_parameter_value("scale")

        # Old node has scale as a value parameter, new node has scale as a percentage
        # ex: old scale= 2.0, new needs to set resize_mode = "percentage" and percentage_scale = 200

        # if old node scale is not connected, we can just set the new parameter.
        # Check if the scale parameter has incoming connections
        is_connected = any(conn.target_parameter_name == "scale" for conn in incoming_connections)

        if not is_connected:
            # Scale parameter is not connected, we can migrate the value

            result = GriptapeNodes.handle_request(
                SetParameterValueRequest(parameter_name="resize_mode", value="percentage", node_name=new_node)
            )
            if isinstance(result, SetParameterValueResultFailure):
                msg = f"{new_node}: Failed to set resize_mode parameter to 'percentage'"
                logger.error(msg)

            result = GriptapeNodes.handle_request(
                SetParameterValueRequest(
                    parameter_name="percentage_scale", value=int(scale_value * 100), node_name=new_node
                )
            )
            if isinstance(result, SetParameterValueResultFailure):
                msg = f"{new_node}: Failed to set percentage_scale parameter to {int(scale_value * 100)}"
                logger.error(msg)
        else:
            # Scale parameter is connected, we need to create a math node to handle the conversion
            math_node_name = f"{new_node}_scale"
            math_node = self._create_new_node(
                node_type="Math",
                node_name=math_node_name,
                node_library="Griptape Nodes Library",
                position="left",
                offset=20,
            )

            # Set the proper settings
            result = GriptapeNodes.handle_request(
                SetParameterValueRequest(parameter_name="operation", value="multiply [A * B]", node_name=math_node)
            )
            if isinstance(result, SetParameterValueResultFailure):
                msg = f"{new_node}: Failed to set resize_mode parameter to 'percentage'"
                logger.error(msg)

            result = GriptapeNodes.handle_request(
                SetParameterValueRequest(parameter_name="B", value=100, node_name=math_node)
            )
            if isinstance(result, SetParameterValueResultFailure):
                msg = f"{new_node}: Failed to set A parameter to {scale_value}"
                logger.error(msg)

            # Connect the math node to the previous node
            self._connect_input(
                incoming_connections=incoming_connections,
                new_node=math_node,
                current_parameter="scale",
                new_node_parameter="A",
            )

            # Connect the math node to the new node
            result = GriptapeNodes.handle_request(
                CreateConnectionRequest(
                    source_node_name=math_node,
                    source_parameter_name="result",
                    target_node_name=new_node,
                    target_parameter_name="percentage_scale",
                )
            )

        return None

    def _get_new_node_position(
        self, position: Literal["left", "right", "top", "bottom"] = "right", offset: int = 10
    ) -> dict:
        # Gets metadata for the node based on the position
        # we want to replace the position.x, position.y, based on the current position, size, and offset

        metadata = self.metadata

        # get the size
        size = metadata["size"]

        # get the current position
        current_position = metadata["position"]

        # Calculate the new position based on the literal position string
        match position:
            case "right":
                new_position = {
                    "x": current_position["x"] + size["width"] + offset,
                    "y": current_position["y"],
                }
            case "left":
                new_position = {
                    "x": current_position["x"] - size["width"] - offset,
                    "y": current_position["y"],
                }
            case "top":
                new_position = {
                    "x": current_position["x"],
                    "y": current_position["y"] - size["height"] - offset,
                }
            case "bottom":
                new_position = {
                    "x": current_position["x"],
                    "y": current_position["y"] + size["height"] + offset,
                }
            case _:
                # Default to right if unknown position
                new_position = {
                    "x": current_position["x"] + size["width"] + offset,
                    "y": current_position["y"],
                }

        # Return only the position metadata
        return {"position": new_position}

    def _create_new_node(
        self,
        node_type: str,
        node_name: str,
        node_library: str | None = None,
        position: Literal["left", "right", "top", "bottom"] = "right",
        offset: int = 10,
    ) -> str:
        # Get the new metadata with updated position
        new_metadata = self._get_new_node_position(position, offset)

        # Create the new node using events
        result = GriptapeNodes.handle_request(
            CreateNodeRequest(
                node_type=node_type,
                specific_library_name=node_library,
                node_name=node_name,
                metadata=new_metadata,
            )
        )

        if not isinstance(result, CreateNodeResultSuccess):
            logger.error("Failed to create node '%s' of type '%s'", node_name, node_type)
            return ""

        return result.node_name

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")
        scale = float(self.get_parameter_value("scale"))
        resample_strategy = str(self.get_parameter_value("resample_strategy"))

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)

        input_image_pil = image_artifact_to_pil(input_image_artifact)

        resample = None
        match resample_strategy:
            case "nearest":
                resample = Resampling.NEAREST
            case "box":
                resample = Resampling.BOX
            case "bilinear":
                resample = Resampling.BILINEAR
            case "hamming":
                resample = Resampling.HAMMING
            case "bicubic":
                resample = Resampling.BICUBIC
            case "lanczos":
                resample = Resampling.LANCZOS
            case _:
                logger.exception("Unknown resampling strategy %s", resample_strategy)

        w, h = input_image_pil.size
        output_image_pil = input_image_pil.resize(
            size=(int(w * scale), int(h * scale)),
            resample=resample,
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/844
        )
        self.set_parameter_value("output_image", pil_to_image_artifact(output_image_pil))
        self.parameter_output_values["output_image"] = pil_to_image_artifact(output_image_pil)
