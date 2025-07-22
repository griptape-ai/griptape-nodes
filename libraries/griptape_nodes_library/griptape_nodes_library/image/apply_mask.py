from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    extract_channel_from_image,
    save_pil_image_to_static_file,
)


class ApplyMask(DataNode):
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
                name="input_mask",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Input mask image.",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.INPUT},
            )
        )
        channel_param = Parameter(
            name="channel",
            type="str",
            tooltip="Generated mask image.",
            default_value="red",
            ui_options={"expander": True, "edit_mask": True, "edit_mask_paint_mask": True},
        )
        channel_param.add_trait(Options(choices=["red", "green", "blue", "alpha"]))
        self.add_parameter(channel_param)

        self.add_parameter(
            Parameter(
                name="output",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Final image with mask applied.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = []

        if self.get_parameter_value("input_image") is None or self.get_parameter_value("input_mask") is None:
            msg = f"{self.name}: Input image and mask are required"
            exceptions.append(Exception(msg))
        return exceptions

    def process(self) -> None:
        input_image = self.get_parameter_value("input_image")
        input_mask = self.get_parameter_value("input_mask")
        channel = self.get_parameter_value("channel")

        if input_image is None or input_mask is None:
            return

        # Normalize dict input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)
        if isinstance(input_mask, dict):
            input_mask = dict_to_image_url_artifact(input_mask)

        # Apply the mask to input image
        self._apply_mask_to_input(input_image, input_mask, channel)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ["input_image", "input_mask"] and value is not None:
            self._handle_parameter_change()

        return super().after_value_set(parameter, value)

    def _handle_parameter_change(self) -> None:
        # Get both current values
        input_image = self.get_parameter_value("input_image")
        input_mask = self.get_parameter_value("input_mask")
        channel = self.get_parameter_value("channel")
        # If we have both inputs, process them
        if input_image is not None and input_mask is not None:
            # Normalize dict inputs to ImageUrlArtifact
            if isinstance(input_image, dict):
                input_image = dict_to_image_url_artifact(input_image)
            if isinstance(input_mask, dict):
                input_mask = dict_to_image_url_artifact(input_mask)

            # Apply the mask to input image
            self._apply_mask_to_input(input_image, input_mask, channel)

    def load_pil_from_url(self, url: str) -> Image.Image:
        """Load image from URL using httpx."""
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))

    def _apply_mask_to_input(self, input_image: ImageUrlArtifact, mask_artifact: Any, channel: str) -> None:
        """Apply mask to input image using specified channel as alpha and set as output_image."""
        # Load input image
        input_pil = self.load_pil_from_url(input_image.value).convert("RGBA")

        # Process the mask
        if isinstance(mask_artifact, dict):
            mask_artifact = dict_to_image_url_artifact(mask_artifact)

        # Load mask
        mask_pil = self.load_pil_from_url(mask_artifact.value)

        # Extract the specified channel as alpha
        alpha = extract_channel_from_image(mask_pil, channel, "mask")

        # Resize alpha to match input image size
        alpha = alpha.resize(input_pil.size, Image.Resampling.NEAREST)

        # Apply alpha channel to input image
        input_pil.putalpha(alpha)
        output_pil = input_pil

        # Save output image and create URL artifact
        output_artifact = save_pil_image_to_static_file(output_pil)
        self.set_parameter_value("output", output_artifact)
        self.publish_update_to_parameter("output", output_artifact)
