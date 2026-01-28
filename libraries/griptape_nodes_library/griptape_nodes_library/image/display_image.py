from io import BytesIO
from typing import Any

import requests
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.retained_mode.griptape_nodes import logger


class DisplayImage(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add parameter for the image
        self.add_parameter(
            ParameterImage(
                name="image",
                default_value=value,
                tooltip="The image to display",
            )
        )
        self.add_parameter(
            ParameterInt(
                name="width",
                default_value=0,
                tooltip="The width of the image",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide": True},
            )
        )
        self.add_parameter(
            ParameterInt(
                name="height",
                default_value=0,
                tooltip="The height of the image",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide": True},
            )
        )

    def _update_output(self) -> None:
        """Update the output image and dimensions."""
        image = self.get_parameter_value("image")
        # Update output value for downstream connections
        self.parameter_output_values["image"] = image
        # Update dimensions
        width, height = self.get_image_dimensions(image) if image else (0, 0)
        self.parameter_output_values["width"] = width
        self.parameter_output_values["height"] = height

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "image":
            self._update_output()
        return super().after_value_set(parameter, value)

    def get_image_dimensions(self, image: ImageArtifact | ImageUrlArtifact) -> tuple[int, int]:
        """Get image dimensions from either ImageArtifact or ImageUrlArtifact."""
        if isinstance(image, ImageArtifact):
            return image.width, image.height
        if isinstance(image, ImageUrlArtifact):
            # Check if it's an SVG file - PIL cannot open SVG files
            # TODO: Add SVG support using cairosvg or similar library to rasterize SVG files: https://github.com/griptape-ai/griptape-nodes/issues/3721
            # and determine dimensions properly
            url_lower = image.value.lower()
            if url_lower.endswith(".svg") or "image/svg+xml" in url_lower:
                # SVG files are vector graphics - return default dimensions
                # since we can't determine dimensions without rasterizing
                logger.debug(f"{self.name}: SVG file detected, cannot determine dimensions without rasterization")
                return 0, 0

            try:
                response = requests.get(image.value, timeout=30)
                response.raise_for_status()

                # Check content type for SVG
                content_type = response.headers.get("content-type", "").lower()
                if "image/svg+xml" in content_type:
                    logger.debug(
                        f"{self.name}: SVG content type detected, cannot determine dimensions without rasterization"
                    )
                    return 0, 0

                image_data = response.content
                pil_image = Image.open(BytesIO(image_data))
            except Exception as e:
                # If PIL cannot identify the image (e.g., SVG), log and return 0,0
                if "cannot identify image file" in str(e).lower():
                    logger.debug(f"{self.name}: Cannot identify image file (may be SVG or unsupported format): {e}")
                    return 0, 0
                # Re-raise other exceptions
                raise
            else:
                return pil_image.width, pil_image.height
        if image:
            logger.warning(f"{self.name}: Could not determine image dimensions, as it is not a valid image")
        return 0, 0

    def process(self) -> None:
        """Process the node during execution."""
        self._update_output()
