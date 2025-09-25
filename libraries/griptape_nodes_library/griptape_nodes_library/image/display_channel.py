from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes_library.image.display_mask import DisplayMask
from griptape_nodes_library.utils.file_utils import generate_filename
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
        filename = generate_filename(
            node_name=self.name,
            suffix="_display_channel",
            extension="png",
        )
        output_artifact = save_pil_image_with_named_filename(mask, filename, "PNG")
        self.set_parameter_value("output", output_artifact)
        self.publish_update_to_parameter("output", output_artifact)
