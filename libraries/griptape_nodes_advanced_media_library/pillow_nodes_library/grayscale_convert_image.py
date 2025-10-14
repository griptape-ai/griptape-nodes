import io
import logging
from datetime import UTC, datetime

from griptape.artifacts import ImageUrlArtifact
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("pillow_nodes_library")


class GrayscaleConvertImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.migrate_message = ParameterMessage(
            variant="warning",
            full_width=True,
            button_text="Create Grayscale Image Node",
            value="This node is being deprecated.\nPlease use the Grayscale Image node from the Griptape Nodes Library.",
            traits={
                Button(label="Create Grayscale Image Node", icon="plus", variant="secondary", on_click=self._migrate)
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
            new_node_type="GrayscaleImage",
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
        cmd.migrate_parameter(self.name, new_node, "output_image", "output")

        return None

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)

        input_image_pil = image_artifact_to_pil(input_image_artifact)
        output_image_pil = input_image_pil.convert("L")

        # Save with standardized filename
        filename = self._generate_filename("png")
        image_io = io.BytesIO()
        output_image_pil.save(image_io, "PNG")
        image_bytes = image_io.getvalue()
        url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, filename)
        output_artifact = ImageUrlArtifact(url)

        self.set_parameter_value("output_image", output_artifact)
        self.parameter_output_values["output_image"] = output_artifact

    def _generate_filename(self, extension: str) -> str:
        """Generate a meaningful filename based on workflow and node information."""
        # Get workflow and node context
        workflow_name = "unknown_workflow"
        node_name = self.name

        # Try to get workflow name from context
        try:
            context_manager = GriptapeNodes.ContextManager()
            workflow_name = context_manager.get_current_workflow_name()
        except Exception as e:
            logger.warning("%s: Error getting workflow name: %s", self.name, e)

        # Clean up names for filename use
        workflow_name = "".join(c for c in workflow_name if c.isalnum() or c in ("-", "_")).rstrip()
        node_name = "".join(c for c in node_name if c.isalnum() or c in ("-", "_")).rstrip()

        # Get current timestamp for cache busting
        timestamp = int(datetime.now(UTC).timestamp())

        # Create filename with meaningful structure and timestamp as query parameter
        filename = f"{workflow_name}_{node_name}_desaturate.{extension}?t={timestamp}"

        return filename
