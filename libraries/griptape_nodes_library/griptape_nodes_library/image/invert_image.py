from typing import Any

from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class InvertImage(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="input_image",
                default_value=None,
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                output_type="ImageArtifact",
                type="ImageArtifact",
                tooltip="The image to invert",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="output",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Inverted image.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "input_image" and value is not None:
            if isinstance(value, dict):
                value = dict_to_image_url_artifact(value)

            # Invert the image
            self._invert_image(value)

    def process(self) -> None:
        # Get input image
        input_image = self.get_parameter_value("input_image")

        if input_image is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)

        # Invert the image
        self._invert_image(input_image)

    def _invert_image(self, image_artifact: ImageUrlArtifact) -> None:
        """Invert the input image and set as output."""
        try:
            # Load image
            image_pil = load_pil_from_url(image_artifact.value)

            # Invert the image based on its mode
            match image_pil.mode:
                case "RGBA":
                    # For RGBA images, invert RGB channels but keep alpha
                    rgb_image = image_pil.convert("RGB")
                    inverted_rgb = Image.eval(rgb_image, lambda x: 255 - x)
                    # Convert back to RGBA and preserve original alpha
                    inverted_image = inverted_rgb.convert("RGBA")
                    # Copy original alpha channel
                    original_alpha = image_pil.getchannel("A")
                    inverted_image.putalpha(original_alpha)
                case "RGB":
                    # Already RGB, invert directly
                    inverted_image = Image.eval(image_pil, lambda x: 255 - x)
                case _:
                    # Convert to RGB for other modes
                    image_to_invert = image_pil.convert("RGB")
                    inverted_image = Image.eval(image_to_invert, lambda x: 255 - x)

            # Save output image and create URL artifact with proper filename
            # Generate a meaningful filename
            filename = generate_filename(
                node_name=self.name,
                suffix="_inverted",
                extension="png",
            )
            output_artifact = save_pil_image_with_named_filename(inverted_image, filename, "PNG")
            self.set_parameter_value("output", output_artifact)
            self.publish_update_to_parameter("output", output_artifact)

        except Exception as e:
            # Log the error and set a meaningful error message
            error_msg = f"Failed to invert image: {e!s}"
            logger.error(f"{self.name}: {error_msg}")
