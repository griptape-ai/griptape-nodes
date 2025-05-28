import hashlib
from io import BytesIO
from typing import Any

import requests
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    save_pil_image_to_static_file,
)


class PaintMask(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_image_hash: str | None = None

        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Optional base image to draw over.",
                ui_options={"expander": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_mask",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Output mask image.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        # Get input image
        image = self.get_parameter_value("image")

        if image is None:
            return

        # Normalize dict input to ImageUrlArtifact
        if isinstance(image, dict):
            image = dict_to_image_url_artifact(image)

        # Check if we need to regenerate the mask
        if not self._needs_mask_regeneration(image):
            return

        # Generate mask (extract alpha channel)
        mask_pil = self.generate_initial_mask(image)

        # Save mask to static folder and wrap in ImageUrlArtifact
        mask_artifact = save_pil_image_to_static_file(mask_pil)

        # Set output
        self.parameter_output_values["output_mask"] = mask_artifact

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        """Regenerate mask when image parameter is updated."""
        if parameter.name == "image" and value is not None:
            # Normalize dict input to ImageUrlArtifact
            if isinstance(value, dict):
                value = dict_to_image_url_artifact(value)

            # Check if we need to regenerate the mask
            if self._needs_mask_regeneration(value):
                # Generate mask (extract alpha channel)
                mask_pil = self.generate_initial_mask(value)

                # Save mask to static folder and wrap in ImageUrlArtifact
                mask_artifact = save_pil_image_to_static_file(mask_pil)

                # Set output
                self.parameter_output_values["output_mask"] = mask_artifact
                self.set_parameter_value("output_mask", mask_artifact)
                modified_parameters_set.add("output_mask")

        return super().after_value_set(parameter, value, modified_parameters_set)

    def _compute_image_hash(self, image_artifact: ImageUrlArtifact) -> str:
        """Compute a hash of the image URL to detect changes."""
        return hashlib.sha256(image_artifact.value.encode("utf-8")).hexdigest()

    def _needs_mask_regeneration(self, image_artifact: ImageUrlArtifact) -> bool:
        """Check if mask needs to be regenerated based on image hash."""
        current_hash = self._compute_image_hash(image_artifact)
        if current_hash != self._last_image_hash:
            self._last_image_hash = current_hash
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
