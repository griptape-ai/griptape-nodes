import logging

import PIL.ImageFilter
from griptape.artifacts import ImageUrlArtifact
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("pillow_nodes_library")


class GaussianBlurImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.migrate_message = ParameterMessage(
            variant="warning",
            full_width=True,
            button_text="Create Gaussian Blur Image Node",
            value="This node is being deprecated.\nPlease use the Gaussian Blur Image node from the Griptape Nodes Library.",
            traits={
                Button(
                    label="Create Gaussian Blur Image Node", icon="plus", variant="secondary", on_click=self._migrate
                )
            },
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
                name="radius",
                default_value=5,
                input_types=["float"],
                type="float",
                tooltip="radius",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _migrate(self, button: Button, button_details: ButtonDetailsMessagePayload) -> NodeMessageResult | None:  # noqa: ARG002
        # Create the new node positioned relative to this one
        new_node_name = f"{self.name}_migrated"

        # Create the new node positioned above this one
        new_node_result = cmd.create_node_relative_to(
            reference_node_name=self.name,
            new_node_type="GaussianBlurImage",
            new_node_name=new_node_name,
            specific_library_name="Griptape Nodes Library",
            offset_side="top_right",
            offset_y=-50,  # Negative offset to go UP from the reference node's top-left corner
            swap=True,
            match_size=True,
        )

        # Extract the node name from the result
        if isinstance(new_node_result, str):
            new_node = new_node_result
        else:
            # If create_node_relative_to failed, new_node_result is the error result
            logger.error("Failed to create node: %s", new_node_result)
            return None

        # Migrate executions
        cmd.migrate_parameter(self.name, new_node, "exec_in", "exec_in")
        cmd.migrate_parameter(self.name, new_node, "exec_out", "exec_out")

        # Migrate simple parameters (no conversion needed)
        cmd.migrate_parameter(self.name, new_node, "input_image", "input_image")
        cmd.migrate_parameter(self.name, new_node, "radius", "radius")
        cmd.migrate_parameter(self.name, new_node, "output_image", "output")

        return None

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")
        radius = float(self.get_parameter_value("radius"))

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)

        input_image_pil = image_artifact_to_pil(input_image_artifact)
        output_image_pil = input_image_pil.filter(PIL.ImageFilter.GaussianBlur(radius=radius))
        output_image_artifact = pil_to_image_artifact(output_image_pil)
        self.set_parameter_value("output_image", output_image_artifact)
        self.parameter_output_values["output_image"] = output_image_artifact
