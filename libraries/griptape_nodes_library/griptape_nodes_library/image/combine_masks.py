from __future__ import annotations

import io
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image, ImageChops

from griptape_nodes.exe_types.core_types import ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class CombineMasks(DataNode):
    """Combine a list of masks into a single consolidated mask (pixel-wise max)."""

    _ALPHA_NEAR_OPAQUE_MIN = 200
    _ALPHA_NEAR_OPAQUE_RANGE = 32
    _EXTREMA_TUPLE_LEN = 2

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            ParameterList(
                name="masks",
                input_types=[
                    "ImageUrlArtifact",
                    "ImageArtifact",
                    "list",
                    "list[ImageUrlArtifact]",
                    "list[ImageArtifact]",
                ],
                default_value=None,
                tooltip="List of mask images to combine into a single mask (union/max).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Masks"},
            )
        )

        self.add_parameter(
            ParameterImage(
                name="output_mask",
                default_value=None,
                tooltip="Combined mask image.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"expander": True, "edit_mask": True, "edit_mask_paint_mask": True},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions: list[Exception] = []

        masks = self.get_parameter_list_value("masks")
        if not masks:
            msg = f"{self.name}: At least one mask is required"
            exceptions.append(ValueError(msg))
            return exceptions

        expected_size: tuple[int, int] | None = None
        for idx, mask_value in enumerate(masks):
            if not isinstance(mask_value, (ImageArtifact, ImageUrlArtifact)):
                msg = f"{self.name}: masks[{idx}] must be an ImageArtifact or ImageUrlArtifact, got {type(mask_value)}."
                exceptions.append(ValueError(msg))
                continue
            try:
                mask_pil = self._load_mask_pil(mask_value)
            except Exception as e:
                msg = f"{self.name}: Failed to load mask at index {idx}: {e}"
                exceptions.append(ValueError(msg))
                continue

            if expected_size is None:
                expected_size = mask_pil.size
                continue

            if mask_pil.size != expected_size:
                msg = (
                    f"{self.name}: All masks must be the same size. "
                    f"Expected {expected_size}, got {mask_pil.size} at index {idx}."
                )
                exceptions.append(ValueError(msg))

        return exceptions or None

    def process(self) -> None:
        self.parameter_output_values["output_mask"] = None

        masks = self.get_parameter_list_value("masks")
        if not masks:
            return

        combined: Image.Image | None = None
        for idx, mask_value in enumerate(masks):
            mask_pil = self._load_mask_pil(mask_value)
            mask_l = self._mask_to_l(mask_pil)
            logger.debug(f"{self.name}: Loaded mask {idx} mode={mask_pil.mode} size={mask_pil.size}")

            if combined is None:
                combined = mask_l
                continue

            # validate sizes again defensively (validate_before_node_run should catch this)
            if mask_l.size != combined.size:
                msg = (
                    f"{self.name}: All masks must be the same size. "
                    f"Expected {combined.size}, got {mask_l.size} at index {idx}."
                )
                raise ValueError(msg)

            combined = ImageChops.lighter(combined, mask_l)

        if combined is None:
            return

        filename = generate_filename(
            node_name=self.name,
            suffix="_combined_mask",
            extension="png",
        )
        output_artifact = save_pil_image_with_named_filename(combined, filename, "PNG")
        self.set_parameter_value("output_mask", output_artifact)
        self.publish_update_to_parameter("output_mask", output_artifact)
        self.parameter_output_values["output_mask"] = output_artifact

    def _load_mask_pil(self, value: Any) -> Image.Image:
        """Load a mask as a PIL image from supported artifact-like inputs."""
        if isinstance(value, ImageUrlArtifact):
            return load_pil_from_url(value.value)

        if isinstance(value, ImageArtifact):
            return Image.open(io.BytesIO(value.to_bytes()))

        if hasattr(value, "to_bytes"):
            return Image.open(io.BytesIO(value.to_bytes()))

        msg = f"Unsupported mask type: {type(value)}"
        raise ValueError(msg)

    def _mask_to_l(self, mask_pil: Image.Image) -> Image.Image:
        """Convert mask image to single-channel (L) grayscale."""
        result = mask_pil.convert("L")
        if mask_pil.mode in {"RGBA", "LA"}:
            alpha = mask_pil.getchannel("A")
            alpha_extrema = alpha.getextrema()
            use_alpha = True
            if isinstance(alpha_extrema, tuple) and len(alpha_extrema) == self._EXTREMA_TUPLE_LEN:
                alpha_min, alpha_max = alpha_extrema
                if isinstance(alpha_min, (int, float)) and isinstance(alpha_max, (int, float)):
                    alpha_range = alpha_max - alpha_min
                    if alpha_min >= self._ALPHA_NEAR_OPAQUE_MIN and alpha_range <= self._ALPHA_NEAR_OPAQUE_RANGE:
                        use_alpha = False
            if use_alpha:
                result = alpha
            elif mask_pil.mode == "RGBA":
                result = mask_pil.getchannel("R")
            else:
                result = mask_pil.getchannel("L")
        elif mask_pil.mode == "L":
            result = mask_pil
        elif mask_pil.mode == "RGB":
            result = mask_pil.convert("L")
        return result
