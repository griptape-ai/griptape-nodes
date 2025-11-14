import io
from typing import Any

from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    save_pil_image_with_named_filename,
)


class MergeImages(ControlNode):
    """Node for merging images together in different layouts with grid options and dynamic image input list."""

    MAX_COLUMNS = 3
    FIT_IMAGES = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.LAYOUT_METHODS = {
            "horizontal": self._process_horizontal_layout,
            "vertical": self._process_vertical_layout,
            "grid": self._process_grid_layout,
            "quick composite": self._process_composite_layout,
        }

        self.LAYOUTS = list(self.LAYOUT_METHODS.keys())
        # Add ParameterList for images (dynamic add/remove, max 4)
        self.add_parameter(
            ParameterList(
                name="Images",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                default_value=None,
                tooltip="Images to merge (add up to 4)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"max": 4, "min": 1, "display_name": "Images"},
            )
        )

        # Add layout parameter (default to grid)
        self.add_parameter(
            Parameter(
                name="layout",
                type="str",
                tooltip="Select how to arrange the images",
                default_value=self.LAYOUTS[0],
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=self.LAYOUTS)},
            )
        )

        # Add output parameter
        self.add_parameter(
            Parameter(
                name="output",
                type="ImageUrlArtifact",
                tooltip="The merged image",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"pulse_on_run": True},
            )
        )

    def get_images(self) -> list:
        images = self.get_parameter_value("Images")
        if images:
            if not isinstance(images, list):
                images = [images]
            return images[:4]  # Enforce max 4
        return []

    def _convert_to_pil_image(self, img: Any) -> Image.Image:
        """Convert various image types to PIL Image."""
        if isinstance(img, dict):
            img = dict_to_image_url_artifact(img)
        if isinstance(img, ImageUrlArtifact):
            img = Image.open(io.BytesIO(img.to_bytes()))
        return img

    def _resize_image(self, img: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """Resize image while preserving aspect ratio."""
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            new_width = target_width
            new_height = int(target_width / img_ratio)
        else:
            new_height = target_height
            new_width = int(target_height * img_ratio)

        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def _process_horizontal_layout(self, images: list[Image.Image]) -> Image.Image:
        # Resize all images to the same height (max height), preserving aspect ratio
        max_height = max(img.height for img in images)
        resized_images = [
            self._resize_image(img, int(img.width * max_height / img.height), max_height) for img in images
        ]
        total_width = sum(img.width for img in resized_images)
        merged = Image.new("RGB", (total_width, max_height))
        x_offset = 0
        for img in resized_images:
            merged.paste(img, (x_offset, 0))
            x_offset += img.width
        return merged

    def _process_vertical_layout(self, images: list[Image.Image]) -> Image.Image:
        # Resize all images to the same width (max width), preserving aspect ratio
        max_width = max(img.width for img in images)
        resized_images = [self._resize_image(img, max_width, int(img.height * max_width / img.width)) for img in images]
        total_height = sum(img.height for img in resized_images)
        merged = Image.new("RGB", (max_width, total_height))
        y_offset = 0
        for img in resized_images:
            merged.paste(img, (0, y_offset))
            y_offset += img.height
        return merged

    def _process_grid_layout(self, images: list[Image.Image]) -> Image.Image:
        n_images = len(images)
        columns = n_images if n_images <= self.MAX_COLUMNS else 2
        rows = (n_images + columns - 1) // columns

        cell_width = int(sum(img.width for img in images) / n_images)
        cell_height = int(sum(img.height for img in images) / n_images)

        merged = Image.new("RGB", (cell_width * columns, cell_height * rows))

        for idx, img in enumerate(images):
            row = idx // columns
            col = idx % columns
            resized_img = self._resize_image(img, cell_width, cell_height)
            x_offset = col * cell_width + (cell_width - resized_img.width) // 2
            y_offset = row * cell_height + (cell_height - resized_img.height) // 2
            merged.paste(resized_img, (x_offset, y_offset))

        return merged

    def _process_composite_layout(self, images: list[Image.Image]) -> Image.Image:
        if not images:
            msg = "No images provided for composite layout"
            raise ValueError(msg)
        # Reverse the order so the last image is at the bottom (like a stack)
        reversed_images = list(reversed(images))
        base = reversed_images[0].copy().convert("RGBA")
        base_width, base_height = base.size
        for img in reversed_images[1:]:
            overlay = img.convert("RGBA") if img.mode != "RGBA" else img.copy()
            resized_overlay = self._resize_image(overlay, base_width, base_height)
            # Center the overlay on the base
            x_offset = (base_width - resized_overlay.width) // 2
            y_offset = (base_height - resized_overlay.height) // 2
            # Composite with alpha blending
            base.paste(resized_overlay, (x_offset, y_offset), resized_overlay)
        # Convert to RGB for consistency with other layouts
        result = Image.new("RGB", base.size, (255, 255, 255))
        result.paste(base, mask=base.split()[3] if base.mode == "RGBA" else None)
        return result

    def process(self) -> None:
        self.parameter_output_values["output"] = None
        images = [self._convert_to_pil_image(img) for img in self.get_images() if img is not None]

        if not images:
            return

        layout = self.get_parameter_value("layout")
        merged = self.LAYOUT_METHODS[layout](images)

        # Save output image with deterministic filename (overwrites same file)
        output_filename = generate_filename(
            node_name=self.name,
            suffix="_merged",
            extension="png",
        )
        url_artifact = save_pil_image_with_named_filename(merged, output_filename, "PNG")
        self.set_parameter_value("output", url_artifact)
        self.parameter_output_values["output"] = url_artifact
