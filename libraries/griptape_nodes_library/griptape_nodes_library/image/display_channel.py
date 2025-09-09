from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.image.display_mask import DisplayMask
from griptape_nodes_library.utils.image_utils import (
    extract_channel_from_image,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class DisplayChannel(DisplayMask):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Remove the old output_mask parameter and add a new "output" parameter
        self.remove_parameter_element_by_name("output_mask")

        self.add_parameter(
            Parameter(
                name="output",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Generated channel image.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Change default channel to red
        channel_param = self.get_parameter_by_name("channel")
        if channel_param is not None:
            channel_param.set_default_value("red")

    def _extract_channel(self, image_artifact: ImageUrlArtifact, channel: str) -> None:
        """Extract a channel from the input image and set as output."""
        # Load image
        image_pil = load_pil_from_url(image_artifact.value)

        # Extract the specified channel as mask
        mask = extract_channel_from_image(image_pil, channel, "image")

        # Save output mask and create URL artifact with proper filename
        # Generate a meaningful filename
        filename = self._generate_filename_with_suffix("_display_channel", "png")
        output_artifact = save_pil_image_with_named_filename(mask, filename, "PNG")
        self.set_parameter_value("output", output_artifact)
        self.publish_update_to_parameter("output", output_artifact)

    def _generate_filename_with_suffix(self, suffix: str, extension: str) -> str:
        """Generate a meaningful filename based on workflow and node information."""
        # Get workflow and node context
        workflow_name = "unknown_workflow"
        node_name = self.name

        # Try to get workflow name from context
        try:
            context_manager = GriptapeNodes.ContextManager()
            workflow_name = context_manager.get_current_workflow_name()
        except Exception as e:
            logger.warning(f"{self.name}: Error getting workflow name: {e}")

        # Clean up names for filename use
        workflow_name = "".join(c for c in workflow_name if c.isalnum() or c in ("-", "_")).rstrip()
        node_name = "".join(c for c in node_name if c.isalnum() or c in ("-", "_")).rstrip()

        # Get current timestamp for cache busting
        timestamp = int(datetime.now(UTC).timestamp())

        # Create filename with meaningful structure and timestamp as query parameter
        filename = f"{workflow_name}_{node_name}{suffix}.{extension}?t={timestamp}"

        return filename
