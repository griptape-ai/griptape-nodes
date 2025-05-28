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
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_mask",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Generated mask image.",
                ui_options={"expander": True, "edit_mask": True},
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

        # Always generate output_image by applying mask to input_image
        self._generate_output_image(input_image)

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "input_image":
            if value is not None:
                # Check and see if the output_mask is set
                output_mask_value = self.get_parameter_value("output_mask")
                if output_mask_value is None:
                    # Normalize dict input to ImageUrlArtifact if needed
                    image_artifact = value
                    if isinstance(value, dict):
                        image_artifact = dict_to_image_url_artifact(value)

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
                    # Use the existing mask from output_mask_value
                    # Normalize input image to ImageUrlArtifact if needed
                    image_artifact = value
                    if isinstance(value, dict):
                        image_artifact = dict_to_image_url_artifact(value)

                    # Apply the existing output_mask_value to the input_image
                    # Load input image
                    input_pil = self.load_pil_from_url(image_artifact.value).convert("RGBA")

                    # Process the existing mask
                    if isinstance(output_mask_value, dict):
                        mask_artifact = dict_to_image_url_artifact(output_mask_value)
                    else:
                        mask_artifact = output_mask_value

                    # Load mask and flatten it (apply alpha if it exists)
                    mask_pil = self.load_pil_from_url(mask_artifact.value)

                    # If mask has alpha, composite it against white background to flatten it
                    if mask_pil.mode in ("RGBA", "LA"):
                        # Create white background
                        background = Image.new("RGB", mask_pil.size, (255, 255, 255))
                        # Composite mask onto white background
                        mask_pil = Image.alpha_composite(background.convert("RGBA"), mask_pil.convert("RGBA"))

                    # Convert to grayscale - now we have the final flattened grayscale values
                    mask_pil = mask_pil.convert("L")

                    # Resize mask to match input image
                    mask_pil = mask_pil.resize(input_pil.size, Image.Resampling.NEAREST)

                    # Use the grayscale values directly as alpha channel
                    # White (255) = opaque, Black (0) = transparent
                    input_pil.putalpha(mask_pil)
                    output_pil = input_pil

                    # Save output image and create URL artifact
                    output_artifact = save_pil_image_to_static_file(output_pil)
                    self.set_parameter_value("output_image", output_artifact)
                    modified_parameters_set.add("output_image")

                # Set something else here - for example:
                # self.some_property = "image_received"
                # or modify the parameter value:
                # self.parameter_values["image"] = value

            logger.info(f"modified_parameters_set: {modified_parameters_set}")
        return super().after_value_set(parameter, value, modified_parameters_set)

    # def after_value_set(
    #     self,
    #     parameter: Parameter,
    #     value: Any,
    #     modified_parameters_set: set[str],
    # ) -> None:
    #     # If connection is made to input_image, always create initial mask and passthrough
    #     if parameter.name == "input_image":
    #         logger.info("input_image connection made")
    #         # Get the connected input image
    #         input_image = self.get_parameter_value("input_image")
    #         if input_image is not None:
    #             logger.info("input_image: ", input_image)
    #             # Normalize dict input to ImageUrlArtifact
    #             if isinstance(input_image, dict):
    #                 input_image = dict_to_image_url_artifact(input_image)
    #                 logger.info("input_image", input_image)

    #             # Always create new mask and set output_image = input_image (passthrough)
    #             self._create_new_mask_and_passthrough(input_image)
    #             modified_parameters_set.add("output_mask")
    #             modified_parameters_set.add("output_image")
    #         else:
    #             logger.info("input_image is None")
    #     return super().after_value_set(parameter, value, modified_parameters_set)

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
        if stored_source_url != input_image.value:
            return True

        return False

    def generate_initial_mask(self, image_artifact: ImageUrlArtifact) -> Image.Image:
        """Extract the alpha channel from a URL-based image."""
        pil_image = self.load_pil_from_url(image_artifact.value).convert("RGBA")
        return pil_image.getchannel("A")

    def load_pil_from_url(self, url: str) -> Image.Image:
        """Download image from URL and return as PIL.Image."""
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))

    def _generate_output_image(self, input_image: ImageUrlArtifact) -> None:
        """Generate output image by applying mask to input image."""
        # Get mask
        mask_artifact = self.get_parameter_value("output_mask")

        if mask_artifact is None:
            return

        # Load input image
        input_pil = self.load_pil_from_url(input_image.value).convert("RGBA")

        # Load and process mask
        if isinstance(mask_artifact, dict):
            mask_artifact = dict_to_image_url_artifact(mask_artifact)

        # Load mask and flatten it (apply alpha if it exists)
        mask_pil = self.load_pil_from_url(mask_artifact.value)

        # If mask has alpha, composite it against white background to flatten it
        if mask_pil.mode in ("RGBA", "LA"):
            # Create white background
            background = Image.new("RGB", mask_pil.size, (255, 255, 255))
            # Composite mask onto white background
            mask_pil = Image.alpha_composite(background.convert("RGBA"), mask_pil.convert("RGBA"))

        # Convert to grayscale - now we have the final flattened grayscale values
        mask_pil = mask_pil.convert("L")

        # Resize mask to match input image
        mask_pil = mask_pil.resize(input_pil.size, Image.Resampling.NEAREST)

        # Use the grayscale values directly as alpha channel
        # White (255) = opaque, Black (0) = transparent
        input_pil.putalpha(mask_pil)
        output_pil = input_pil

        # Save output image
        output_artifact = save_pil_image_to_static_file(output_pil)

        # Set output image parameter
        self.set_parameter_value("output_image", output_artifact)

    def _create_new_mask_and_passthrough(self, input_image: ImageUrlArtifact) -> None:
        """Create new mask and set output_image = input_image (passthrough)."""
        # Generate initial mask from alpha channel
        mask_pil = self.generate_initial_mask(input_image)

        # Save mask to static folder and wrap in ImageUrlArtifact
        mask_artifact = save_pil_image_to_static_file(mask_pil)

        # Store the input image URL in metadata for tracking
        metadata = getattr(mask_artifact, "metadata", {}) or {}
        metadata["source_image_url"] = input_image.value

        # Set output mask parameter
        self.set_parameter_value("output_mask", mask_artifact)

        # Set output_image = input_image (passthrough)
        self.set_parameter_value("output_image", input_image)

    def _is_mask_edited(self, output_mask: ImageUrlArtifact) -> bool:
        # Check if the mask has been manually edited
        if isinstance(output_mask, dict):
            # Handle dict representation
            return output_mask.get("metadata", {}).get("maskEdited", False)
        # Handle ImageUrlArtifact with metadata attribute
        metadata = getattr(output_mask, "metadata", {})
        return isinstance(metadata, dict) and metadata.get("maskEdited", False)

    def _apply_existing_mask_to_input(self, input_image: ImageUrlArtifact) -> None:
        """Apply existing edited mask to new input_image and save as output_image."""
        # Get existing mask
        output_mask = self.get_parameter_value("output_mask")

        if output_mask is None:
            return

        # Load input image
        input_pil = self.load_pil_from_url(input_image.value).convert("RGBA")

        # Load and process mask
        if isinstance(output_mask, dict):
            output_mask = dict_to_image_url_artifact(output_mask)

        # Load mask and flatten it (apply alpha if it exists)
        mask_pil = self.load_pil_from_url(output_mask.value)

        # If mask has alpha, composite it against white background to flatten it
        if mask_pil.mode in ("RGBA", "LA"):
            # Create white background
            background = Image.new("RGB", mask_pil.size, (255, 255, 255))
            # Composite mask onto white background
            mask_pil = Image.alpha_composite(background.convert("RGBA"), mask_pil.convert("RGBA"))

        # Convert to grayscale - now we have the final flattened grayscale values
        mask_pil = mask_pil.convert("L")

        # Resize mask to match input image
        mask_pil = mask_pil.resize(input_pil.size, Image.Resampling.NEAREST)

        # Use the grayscale values directly as alpha channel
        # White (255) = opaque, Black (0) = transparent
        input_pil.putalpha(mask_pil)
        output_pil = input_pil

        # Save output image
        output_artifact = save_pil_image_to_static_file(output_pil)

        # Set output image parameter
        self.set_parameter_value("output_image", output_artifact)
