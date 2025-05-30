from io import BytesIO
from typing import Any

import requests
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    save_pil_image_to_static_file,
)


class PaintMask(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="input_image",
                default_value=None,
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                output_type="ImageArtifact",
                type="ImageArtifact",
                tooltip="The image to display",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.INPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_mask",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Generated mask image.",
                ui_options={"expander": True, "edit_mask": True, "edit_mask_paint_mask": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Final image with mask applied.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        # Get input image
        input_image = self.get_parameter_value("input_image")

        if input_image is None:
            return

        # Normalize dict input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)

        # Check if we need to generate a new mask
        if self._needs_mask_regeneration(input_image):
            # Generate mask (extract alpha channel)
            mask_pil = self.generate_initial_mask(input_image)

            # Save mask to static folder and wrap in ImageUrlArtifact
            mask_artifact = save_pil_image_to_static_file(mask_pil)

            # Store the input image URL in metadata for tracking
            metadata = getattr(mask_artifact, "metadata", {}) or {}
            metadata["source_image_url"] = input_image.value

            # Set output mask
            self.parameter_output_values["output_mask"] = mask_artifact

        # Get the current mask
        mask_artifact = self.get_parameter_value("output_mask")
        if mask_artifact is not None:
            # Apply the mask to input image
            self._apply_mask_to_input(input_image, mask_artifact)

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "input_image":
            if value is not None:
                # Normalize input image to ImageUrlArtifact if needed
                image_artifact = value
                if isinstance(value, dict):
                    image_artifact = dict_to_image_url_artifact(value)

                # Check and see if the output_mask is set
                output_mask_value = self.get_parameter_value("output_mask")
                if output_mask_value is None:
                    # Create a new mask for output_mask and set that value
                    output_mask_value = self.generate_initial_mask(image_artifact)
                    output_mask_artifact = save_pil_image_to_static_file(output_mask_value)

                    # Create a dictionary representation with metadata for tracking
                    mask_dict = {
                        "type": "ImageUrlArtifact",
                        "value": output_mask_artifact.value,
                        "metadata": {"source_image_url": image_artifact.value},
                    }

                    self.set_parameter_value("output_mask", mask_dict)
                    modified_parameters_set.add("output_mask")

                    # Set output_image to the input_image
                    self.set_parameter_value("output_image", value)
                    modified_parameters_set.add("output_image")
                else:
                    # Update the metadata of the existing mask to reference the new input image
                    if isinstance(output_mask_value, dict):
                        # Update metadata in the existing dict
                        if "metadata" not in output_mask_value:
                            output_mask_value["metadata"] = {}
                        output_mask_value["metadata"]["source_image_url"] = image_artifact.value
                        # Update the mask value to ensure changes are saved
                        self.set_parameter_value("output_mask", output_mask_value)
                        modified_parameters_set.add("output_mask")
                    else:
                        # Convert ImageUrlArtifact to dict with metadata
                        mask_dict = {
                            "type": "ImageUrlArtifact",
                            "value": output_mask_value.value,
                            "metadata": {"source_image_url": image_artifact.value},
                        }
                        self.set_parameter_value("output_mask", mask_dict)
                        modified_parameters_set.add("output_mask")

                    # Apply the mask to input image
                    self._apply_mask_to_input(image_artifact, output_mask_value)
                    modified_parameters_set.add("output_image")

        elif parameter.name == "output_mask" and value is not None:
            # Get the input image
            input_image = self.get_parameter_value("input_image")
            if input_image is not None:
                # Normalize input image to ImageUrlArtifact if needed
                if isinstance(input_image, dict):
                    input_image = dict_to_image_url_artifact(input_image)

                # Apply the mask to input image
                self._apply_mask_to_input(input_image, value)
                modified_parameters_set.add("output_image")

        logger.info(f"modified_parameters_set: {modified_parameters_set}")
        return super().after_value_set(parameter, value, modified_parameters_set)

    def _needs_mask_regeneration(self, input_image: ImageUrlArtifact) -> bool:
        """Check if mask needs to be regenerated based on mask editing status and source image."""
        # Get current output mask
        output_mask = self.get_parameter_value("output_mask")

        if output_mask is None:
            # No mask exists, need to generate one
            return True

        # Check if the mask has been manually edited
        if isinstance(output_mask, dict):
            # Handle dict representation
            if output_mask.get("metadata", {}).get("maskEdited", False):
                return False
            # Check if source image has changed
            stored_source_url = output_mask.get("metadata", {}).get("source_image_url")
        else:
            # Handle ImageUrlArtifact with metadata attribute
            metadata = getattr(output_mask, "metadata", {})
            if isinstance(metadata, dict) and metadata.get("maskEdited", False):
                return False
            # Check if source image has changed
            stored_source_url = metadata.get("source_image_url") if isinstance(metadata, dict) else None

        # If source image URL has changed, regenerate mask
        return stored_source_url != input_image.value

    def generate_initial_mask(self, image_artifact: ImageUrlArtifact) -> Image.Image:
        """Extract the alpha channel from a URL-based image."""
        pil_image = self.load_pil_from_url(image_artifact.value).convert("RGBA")
        return pil_image.getchannel("A")

    def load_pil_from_url(self, url: str) -> Image.Image:
        """Download image from URL and return as PIL.Image."""
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))

    def _apply_mask_to_input(self, input_image: ImageUrlArtifact, mask_artifact: Any) -> None:
        """Apply mask to input image using red channel as alpha and set as output_image."""
        # Load input image
        input_pil = self.load_pil_from_url(input_image.value).convert("RGBA")

        # Process the mask
        if isinstance(mask_artifact, dict):
            mask_artifact = dict_to_image_url_artifact(mask_artifact)

        # Load mask
        mask_pil = self.load_pil_from_url(mask_artifact.value)

        # Extract red channel and use as alpha
        if mask_pil.mode == "RGB":
            # Get red channel
            r, _, _ = mask_pil.split()
            alpha = r
        elif mask_pil.mode == "RGBA":
            # Get red channel
            r, _, _, _ = mask_pil.split()
            alpha = r
        else:
            # Convert to RGB first
            mask_pil = mask_pil.convert("RGB")
            r, _, _ = mask_pil.split()
            alpha = r

        # Resize alpha to match input image
        alpha = alpha.resize(input_pil.size, Image.Resampling.NEAREST)

        # Apply alpha channel to input image
        input_pil.putalpha(alpha)
        output_pil = input_pil

        # Save output image and create URL artifact
        output_artifact = save_pil_image_to_static_file(output_pil)
        self.set_parameter_value("output_image", output_artifact)
