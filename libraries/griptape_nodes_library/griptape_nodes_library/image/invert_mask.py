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


class InvertMask(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="input_mask",
                default_value=None,
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                output_type="ImageArtifact",
                type="ImageArtifact",
                tooltip="The mask to invert",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_mask",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Inverted mask image.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "input_mask" and value is not None:
            if isinstance(value, dict):
                value = dict_to_image_url_artifact(value)

            # Invert the mask
            self._invert_mask(value)

    def process(self) -> None:
        # Get input mask
        input_mask = self.get_parameter_value("input_mask")

        if input_mask is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(input_mask, dict):
            input_mask = dict_to_image_url_artifact(input_mask)

        # Invert the mask
        self._invert_mask(input_mask)

    def _invert_mask(self, mask_artifact: ImageUrlArtifact) -> None:
        """Invert the input mask and set as output_mask."""
        try:
            # Load mask
            mask_pil = load_pil_from_url(mask_artifact.value)
            logger.debug(f"{self.name}: Processing mask with mode {mask_pil.mode}, size {mask_pil.size}")

            # Convert to grayscale first to ensure consistent processing
            if mask_pil.mode == "RGBA":
                # For RGBA images, use the alpha channel
                mask_to_invert = mask_pil.getchannel("A")
                logger.debug(f"{self.name}: Using alpha channel from RGBA image")
            elif mask_pil.mode == "RGB":
                # For RGB images, convert to grayscale
                mask_to_invert = mask_pil.convert("L")
                logger.debug(f"{self.name}: Converted RGB to grayscale")
            elif mask_pil.mode == "L":
                # Already grayscale
                mask_to_invert = mask_pil
                logger.debug(f"{self.name}: Using grayscale image directly")
            else:
                # For other modes, convert to grayscale
                mask_to_invert = mask_pil.convert("L")
                logger.debug(f"{self.name}: Converted {mask_pil.mode} to grayscale")

            # Invert the mask
            inverted_mask = Image.eval(mask_to_invert, lambda x: 255 - x)
            logger.debug(f"{self.name}: Inverted mask, result mode {inverted_mask.mode}")

            # Ensure output is in grayscale mode
            if inverted_mask.mode != "L":
                inverted_mask = inverted_mask.convert("L")
                logger.debug(f"{self.name}: Converted output to grayscale")

            # Save output mask and create URL artifact with proper filename
            # Generate a meaningful filename
            filename = generate_filename(
                node_name=self.name,
                suffix="_inverted_mask",
                extension="png",
            )
            output_artifact = save_pil_image_with_named_filename(inverted_mask, filename, "PNG")
            self.set_parameter_value("output_mask", output_artifact)
            self.publish_update_to_parameter("output_mask", output_artifact)
            logger.debug(f"{self.name}: Successfully saved inverted mask")

        except Exception as e:
            # Log the error and set a meaningful error message
            error_msg = f"Failed to invert mask: {e!s}"
            logger.error(f"{self.name}: {error_msg}")
            import traceback

            logger.debug(f"{self.name}: {traceback.format_exc()}")
