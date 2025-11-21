from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    apply_mask_transformations,
    dict_to_image_url_artifact,
    extract_channel_from_image,
    save_pil_image_with_named_filename,
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
        self.add_parameter(ParameterBool(name="invert_mask", default_value=False))
        self.add_parameter(ParameterFloat(name="grow_shrink", default_value=0, slider=True, min_val=-100, max_val=100))
        self.add_parameter(ParameterFloat(name="blur_mask", default_value=0, slider=True, min_val=0, max_val=100))
        self.add_parameter(
            ParameterBool(
                name="apply_mask_blur_to_edges", default_value=False, tooltip="apply blur_mask to image edges"
            )
        )

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
        super().after_value_set(parameter, value)

        if parameter.name in ["input_image", "input_mask"] and value is not None:
            self._handle_parameter_change()
        elif parameter.name in ["channel", "invert_mask", "grow_shrink", "blur_mask", "apply_mask_blur_to_edges"]:
            # When transform parameters change, re-apply the mask
            input_image = self.get_parameter_value("input_image")
            input_mask = self.get_parameter_value("input_mask")
            channel = self.get_parameter_value("channel")

            if input_image is None or input_mask is None:
                return

            if isinstance(input_image, dict):
                input_image = dict_to_image_url_artifact(input_image)
            if isinstance(input_mask, dict):
                input_mask = dict_to_image_url_artifact(input_mask)

            self._apply_mask_to_input(input_image, input_mask, channel)

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

    def _create_edge_mask(self, size: tuple[int, int], fade_distance: float) -> Image.Image:
        """Create an edge mask that fades from transparent at edges to opaque at center.

        Args:
            size: (width, height) of the mask
            fade_distance: Distance in pixels from edge where fade occurs

        Returns:
            PIL Image (grayscale) with edge fade
        """
        width, height = size
        mask = Image.new("L", size, 255)

        # Create gradient arrays for horizontal and vertical fades
        for y in range(height):
            for x in range(width):
                # Calculate distance from each edge
                dist_from_left = x
                dist_from_right = width - x - 1
                dist_from_top = y
                dist_from_bottom = height - y - 1

                # Find minimum distance to any edge
                min_dist = min(dist_from_left, dist_from_right, dist_from_top, dist_from_bottom)

                # Calculate alpha based on distance and fade_distance
                if min_dist >= fade_distance:
                    alpha_value = 255
                else:
                    # Linear fade from 0 at edge to 255 at fade_distance
                    alpha_value = int((min_dist / fade_distance) * 255)

                mask.putpixel((x, y), alpha_value)

        return mask

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

        # Apply mask transformations
        grow_shrink = self.get_parameter_value("grow_shrink")
        invert_mask = self.get_parameter_value("invert_mask")
        blur_mask = self.get_parameter_value("blur_mask")
        alpha = apply_mask_transformations(
            alpha,
            grow_shrink=grow_shrink,
            invert=invert_mask,
            blur_radius=blur_mask,
            context_name=self.name,
        )

        # Apply edge blur if enabled
        apply_edge_blur = self.get_parameter_value("apply_mask_blur_to_edges")
        if apply_edge_blur and blur_mask > 0:
            edge_mask = self._create_edge_mask(input_pil.size, blur_mask)
            # Combine edge mask with alpha channel by multiplying
            alpha_array = list(alpha.getdata())
            edge_array = list(edge_mask.getdata())
            combined = [int(a * e / 255) for a, e in zip(alpha_array, edge_array, strict=True)]
            alpha.putdata(combined)

        # Apply alpha channel to input image
        input_pil.putalpha(alpha)

        # Save output image and create URL artifact with proper filename
        filename = generate_filename(
            node_name=self.name,
            suffix="_apply_mask",
            extension="png",
        )
        output_artifact = save_pil_image_with_named_filename(input_pil, filename, "PNG")
        self.set_parameter_value("output", output_artifact)
        self.publish_update_to_parameter("output", output_artifact)
