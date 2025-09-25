import base64
from io import BytesIO
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from griptape.artifacts import ImageUrlArtifact, JsonArtifact
from PIL import Image, ImageEnhance

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.color_utils import parse_color_to_rgba
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
)

CANVAS_DIMENSIONS = {
    "2K Full": {"width": 2048, "height": 1080},
    "2K Flat": {"width": 1998, "height": 1080},
    "2K Scope": {"width": 2048, "height": 858},
    "4K Full": {"width": 4096, "height": 2160},
    "4K Flat": {"width": 3996, "height": 2160},
    "4K Scope": {"width": 4096, "height": 1716},
    "HD (16:9)": {"width": 1920, "height": 1080},
    "UHD (4K, 16:9)": {"width": 3840, "height": 2160},
    "Square 2K": {"width": 2048, "height": 2048},
    "Square 4K": {"width": 4096, "height": 4096},
    "YouTube Shorts / TikTok / Reels": {"width": 1080, "height": 1920},
    "Instagram Square": {"width": 1080, "height": 1080},
    "Instagram Portrait": {"width": 1080, "height": 1350},
    "Twitter Landscape": {"width": 1600, "height": 900},
    "Twitter Portrait": {"width": 1080, "height": 1350},
    "Facebook Cover": {"width": 820, "height": 312},
    "Custom": {"width": None, "height": None},
}

BASE_CANVAS_OPTIONS = [*list(CANVAS_DIMENSIONS.keys())]

default_svg = """<svg width="1920" height="1080" xmlns="http://www.w3.org/2000/svg">
<rect width="1920" height="1080" fill="#fffffa"/>
</svg>"""
default_svg_base64 = base64.b64encode(default_svg.encode("utf-8")).decode("utf-8")


UUID_HEX_LENGTH = 32  # Length of UUID without dashes (e.g., "81222ddd97cd4e32b1005cda0178d193")


class ImageBash(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Add flag to prevent sync during initialization
        self._initializing = True

        with ParameterGroup(name="canvas_details", ui_options={"collapsed": True}) as canvas_details_group:
            self.canvas_size = Parameter(
                name="canvas_size",
                default_value="Custom",
                type="string",
                tooltip="The size of the canvas to create",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            self.canvas_size.add_trait(Options(choices=BASE_CANVAS_OPTIONS))
            self.canvas_width = Parameter(
                name="width",
                default_value=1920,
                input_types=["int"],
                type="int",
                tooltip="The width of the image to create",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )

            self.canvas_height = Parameter(
                name="height",
                default_value=1080,
                input_types=["int"],
                type="int",
                tooltip="The height of the image to create",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )

            self.background_color = Parameter(
                name="background_color",
                default_value="#ffffff",
                type="str",
                tooltip="Background color for the canvas (hex color like #ffffff or #fffffa)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={ColorPicker(format="hex")},
            )
        self.add_node_element(canvas_details_group)

        self.add_parameter(
            ParameterList(
                name="input_images",
                default_value=None,
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="The images to use for the image",
                allowed_modes={ParameterMode.INPUT},
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

        # Create a proper default placeholder SVG

        self.add_parameter(
            Parameter(
                name="bash_image",
                default_value={
                    "value": f"data:image/svg+xml;base64,{default_svg_base64}",
                    "name": "Canvas Project",
                    "meta": {
                        "input_images": [],
                        "konva_json": {"images": [], "lines": []},
                        "viewport": {"x": 0, "y": 0, "scale": 1.0, "center_x": 960, "center_y": 540},
                    },
                },
                type="JsonArtifact",
                tooltip="Open the editor to create an image",
                ui_options={
                    "button": True,
                    "button_icon": "images",
                    "button_label": "Open Image Bash Editor",
                    "modal": "ImageBashModal",
                },
                allowed_modes={ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="comp_on_run",
                type="bool",
                default_value=True,
                tooltip=(
                    "If enabled, this node recomposes layers from Image Bash metadata when processing. "
                    "If disabled, it outputs the current image from the Image Bash editor."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Mark initialization as complete
        self._initializing = False

    def _get_image_dimensions(self, image_url: str) -> tuple[int, int]:
        """Get the width and height of an image from its URL."""
        try:
            response = httpx.get(image_url, timeout=30)
            response.raise_for_status()

            with Image.open(BytesIO(response.content)) as img:
                return img.size  # Returns (width, height)
        except Exception:
            # Fallback to default dimensions if we can't load the image
            return (400, 300)

    def _get_canvas_dimensions(self) -> tuple[int, int]:
        """Get canvas dimensions based on canvas_size parameter."""
        canvas_size = self.get_parameter_value("canvas_size")
        if canvas_size == "custom":
            # For custom, use the current width/height parameter values
            width = self.get_parameter_value("width") or 1920
            height = self.get_parameter_value("height") or 1080
            return (width, height)
        if canvas_size in CANVAS_DIMENSIONS:
            dimensions = CANVAS_DIMENSIONS[canvas_size]
            # Handle None values (for Custom)
            if dimensions["width"] is None or dimensions["height"] is None:
                # Fallback to current parameter values
                width = self.get_parameter_value("width") or 1920
                height = self.get_parameter_value("height") or 1080
                return (width, height)
            return (dimensions["width"], dimensions["height"])
        # Fallback to HD
        dimensions = CANVAS_DIMENSIONS["HD"]
        return (dimensions["width"], dimensions["height"])

    def _get_existing_background_color(self, bash_image_value: Any) -> str:  # noqa: ARG002
        """Get the current background color from the parameter."""
        return self.get_parameter_value("background_color") or "#ffffff"

    def _create_viewport_metadata(self, canvas_width: int, canvas_height: int) -> dict:
        """Create viewport metadata for the given canvas dimensions."""
        return {
            "x": 0,
            "y": 0,
            "scale": 1.0,
            "center_x": canvas_width // 2,
            "center_y": canvas_height // 2,
        }

    def _update_bash_image_metadata(  # noqa: PLR0913
        self,
        bash_image_value: Any,
        input_images: list,
        konva_images: list,
        existing_konva: dict,
        canvas_width: int,
        canvas_height: int,
        *,  # Force keyword arguments after this point
        preserve_existing: bool = False,
    ) -> None:
        """Update the bash_image metadata with new values."""
        if isinstance(bash_image_value, dict):
            if "meta" not in bash_image_value:
                bash_image_value["meta"] = {}

            if not preserve_existing:
                bash_image_value["meta"]["input_images"] = input_images
                bash_image_value["meta"]["konva_json"] = {
                    "images": konva_images,
                    "lines": existing_konva.get("lines", []),
                }

            # Store viewport settings
            bash_image_value["meta"]["viewport"] = self._create_viewport_metadata(canvas_width, canvas_height)

            self.set_parameter_value("bash_image", bash_image_value)
            self.publish_update_to_parameter("bash_image", bash_image_value)
        else:
            # For ImageUrlArtifact
            meta = getattr(bash_image_value, "meta", {})
            if not isinstance(meta, dict):
                meta = {}

            if not preserve_existing:
                meta["input_images"] = input_images
                meta["konva_json"] = {"images": konva_images, "lines": existing_konva.get("lines", [])}

            # Store viewport settings
            meta["viewport"] = self._create_viewport_metadata(canvas_width, canvas_height)

            bash_image_value.meta = meta
            self.set_parameter_value("bash_image", bash_image_value)
            self.publish_update_to_parameter("bash_image", bash_image_value)
            self.parameter_output_values["bash_image"] = bash_image_value

    def _process_input_image(self, img: Any, i: int, existing_input_images: list) -> dict | None:
        """Process a single input image and return its metadata."""
        # Handle different types of input
        if isinstance(img, dict):
            img_artifact = dict_to_image_url_artifact(img)
        elif hasattr(img, "value"):  # ImageArtifact or ImageUrlArtifact
            img_artifact = img
        elif isinstance(img, list):
            return None
        else:
            return None

        # Get the image URL
        try:
            image_url = img_artifact.value
        except AttributeError:
            return None

        # Try to preserve existing name, otherwise generate new one
        image_name = self._get_image_name(image_url, i, existing_input_images)

        return {
            "id": f"source-img-{i + 1}",
            "url": image_url,
            "name": image_name,
        }

    def _get_image_name(self, image_url: str, i: int, existing_input_images: list) -> str:
        """Get or generate a name for an image."""
        # Try to preserve existing name from previous metadata
        for existing_input in existing_input_images:
            if existing_input.get("url") == image_url:
                existing_name = existing_input.get("name")
                # Only preserve if it's not a UUID
                if existing_name and not (
                    len(existing_name) == UUID_HEX_LENGTH and all(c in "0123456789abcdef" for c in existing_name)
                ):
                    return existing_name

        # Generate new name from filename
        try:
            parsed_url = urlparse(image_url)
            filename = unquote(parsed_url.path.split("/")[-1])
            # Remove extension and query params
            if filename and "." in filename:
                image_name = filename.split(".")[0].split("?")[0]
            else:
                image_name = f"Image {i + 1}"
        except Exception:
            image_name = f"Image {i + 1}"

        return image_name

    def _is_brush_layer(self, existing_img: dict) -> bool:
        """Check if a konva image is a brush layer."""
        existing_type = existing_img.get("type", "")
        existing_id = existing_img.get("id", "")
        existing_source_id = existing_img.get("source_id", "")

        return (
            existing_type == "brush"
            or existing_source_id.startswith("brush-")
            or "brush" in existing_source_id.lower()
            or existing_id.startswith("layer-")
        )

    def _calculate_image_fit_and_position(
        self, img_width: int, img_height: int, canvas_width: int, canvas_height: int
    ) -> tuple[float, float, float, float]:
        """Calculate the scale and position to fit an image within the canvas while maintaining aspect ratio."""
        # Calculate the scale needed to fit the image within the canvas
        # No padding - images appear at their default size
        padding_factor = 0.0
        max_width = canvas_width * (1 - padding_factor)
        max_height = canvas_height * (1 - padding_factor)

        # Calculate scale factors for both dimensions
        scale_x = max_width / img_width if img_width > max_width else 1.0
        scale_y = max_height / img_height if img_height > max_height else 1.0

        # Use the smaller scale to maintain aspect ratio
        scale = min(scale_x, scale_y)

        # Calculate position to center the image
        # In Konva, x and y represent the center point of the image
        x = canvas_width / 2  # Center of canvas horizontally
        y = canvas_height / 2  # Center of canvas vertically

        return scale, scale, x, y

    def _create_konva_layer(self, input_img: dict, i: int, canvas_width: int, canvas_height: int) -> dict:
        """Create a new konva layer for an input image."""
        img_width, img_height = self._get_image_dimensions(input_img["url"])
        scale_x, scale_y, x, y = self._calculate_image_fit_and_position(
            img_width, img_height, canvas_width, canvas_height
        )

        # Extract filename from URL for the layer name
        try:
            parsed_url = urlparse(input_img["url"])
            filename = unquote(parsed_url.path.split("/")[-1])
            # Remove extension and query params
            layer_name = filename.split(".")[0].split("?")[0]
        except Exception:
            # Fallback name if URL parsing fails
            layer_name = f"Image Layer {i + 1}"

        return {
            "id": f"canvas-img-{i + 1}",
            "source_id": input_img["id"],
            "src": input_img["url"],
            "x": x,
            "y": y,
            "width": img_width,  # Keep original dimensions
            "height": img_height,  # Keep original dimensions
            "rotation": 0,
            "scaleX": scale_x,  # Apply scaling to fit canvas
            "scaleY": scale_y,  # Apply scaling to fit canvas
            "type": "image",  # Required to distinguish from brush layers
            "name": layer_name,  # Display name based on filename
            "opacity": 1,  # Full opacity by default
            "visible": True,  # Visible by default
            "order": i + 1,  # Layer order based on index
        }

    def _build_konva_images(
        self, input_images: list, existing_konva: dict, canvas_width: int, canvas_height: int
    ) -> list:
        """Build the konva images array from input images and existing konva data."""
        # Preserve brush layers
        konva_images = [
            existing_img.copy()
            for existing_img in existing_konva.get("images", [])
            if self._is_brush_layer(existing_img)
        ]

        # Create/update konva layers for current input_images
        for i, input_img in enumerate(input_images):
            # Try to find existing konva layer for this image
            existing_konva_img = None
            for existing_img in existing_konva.get("images", []):
                if existing_img.get("source_id") == input_img["id"]:
                    existing_konva_img = existing_img
                    break

            if existing_konva_img:
                # Preserve ALL existing layer data, including scale, rotation, position, etc.
                konva_img = existing_konva_img.copy()
                konva_img["source_id"] = input_img["id"]
                # Ensure all required properties are present
                if "scaleX" not in konva_img:
                    konva_img["scaleX"] = 1.0
                if "scaleY" not in konva_img:
                    konva_img["scaleY"] = 1.0
                if "rotation" not in konva_img:
                    konva_img["rotation"] = 0
                konva_images.append(konva_img)
            else:
                # Create new layer
                konva_images.append(self._create_konva_layer(input_img, i, canvas_width, canvas_height))

        return konva_images

    def _sync_metadata_with_input_images(self) -> None:
        """Sync the bash_image metadata with the current input_images state."""
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is None:
            self._create_new_bash_image()
            return

        # Get current input_images
        current_input_images = self.get_parameter_value("input_images") or []

        # Get existing metadata
        if isinstance(bash_image_value, dict):
            existing_meta = bash_image_value.get("meta", {})
        else:
            existing_meta = getattr(bash_image_value, "meta", {})

        existing_konva = existing_meta.get("konva_json", {"images": [], "lines": []})
        existing_input_images = existing_meta.get("input_images", [])

        # Get canvas dimensions
        canvas_width, canvas_height = self._get_canvas_dimensions()

        # Create new input_images array from current input_images
        input_images = [
            processed_img
            for i, img in enumerate(current_input_images)
            if (processed_img := self._process_input_image(img, i, existing_input_images))
        ]

        # Build new konva_images array
        konva_images = self._build_konva_images(input_images, existing_konva, canvas_width, canvas_height)

        # Update metadata
        self._update_bash_image_metadata(
            bash_image_value,
            input_images,
            konva_images,
            existing_konva,
            canvas_width,
            canvas_height,
        )

    def _handle_input_images_removed(self) -> None:
        """Handle the case when all input images are removed."""
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is None:
            return

        # Get canvas dimensions and background color
        canvas_width, canvas_height = self._get_canvas_dimensions()
        background_color = self.get_parameter_value("background_color") or "#ffffff"

        # Create new placeholder with background color
        svg_content = f"""<svg width="{canvas_width}" height="{canvas_height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{canvas_width}" height="{canvas_height}" fill="{background_color}"/>
</svg>"""
        new_placeholder_url = (
            f"data:image/svg+xml;base64,{base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')}"
        )

        # Get existing konva data
        if isinstance(bash_image_value, dict):
            existing_konva = bash_image_value.get("meta", {}).get("konva_json", {"images": [], "lines": []})
            bash_image_value["value"] = new_placeholder_url
        else:
            existing_konva = getattr(bash_image_value, "meta", {}).get("konva_json", {"images": [], "lines": []})
            bash_image_value.value = new_placeholder_url

        # Keep only brush layers (remove image layers)
        brush_layers = [img.copy() for img in existing_konva.get("images", []) if self._is_brush_layer(img)]

        # Update metadata using common method
        self._update_bash_image_metadata(
            bash_image_value,
            [],  # Empty input_images
            brush_layers,  # Only brush layers
            existing_konva,
            canvas_width,
            canvas_height,
        )

    def _create_new_bash_image(self) -> None:
        # Get the list of images from the ParameterList
        images_list = self.get_parameter_value("input_images") or []

        # Create input_images array from the images ParameterList
        input_images = []
        for i, img in enumerate(images_list):
            if isinstance(img, dict):
                img_artifact = dict_to_image_url_artifact(img)
            else:
                img_artifact = img

            # Use the existing helper method for name generation
            image_name = self._get_image_name(img_artifact.value, i, [])
            input_images.append({"id": f"source-img-{i + 1}", "url": img_artifact.value, "name": image_name})

        # Get canvas dimensions and background color from parameters
        canvas_width, canvas_height = self._get_canvas_dimensions()
        background_color = self.get_parameter_value("background_color") or "#ffffff"

        # Create basic Konva JSON structure with image elements using existing helper
        konva_images = [
            self._create_konva_layer(input_img, i, canvas_width, canvas_height)
            for i, input_img in enumerate(input_images)
        ]

        konva_json = {"images": konva_images, "lines": []}

        # Use a simple placeholder URL - the actual canvas is defined by width/height and konva_json
        svg_content = f"""<svg width="{canvas_width}" height="{canvas_height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{canvas_width}" height="{canvas_height}" fill="{background_color}"/>
</svg>"""
        placeholder_url = f"data:image/svg+xml;base64,{base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')}"

        bash_image_artifact = JsonArtifact(
            {
                "value": placeholder_url,
                "name": "Canvas Project",
                "meta": {
                    "input_images": input_images,
                    "konva_json": konva_json,
                    "viewport": self._create_viewport_metadata(canvas_width, canvas_height),
                },
            }
        )
        self.set_parameter_value("bash_image", bash_image_artifact)

    def _handle_canvas_size_change(self, value: Any) -> None:
        """Handle canvas_size parameter changes."""
        if value == "Custom":
            # 2. If user modifies canvas_size to custom, let them specify width and height
            # Don't publish updates when switching to custom - preserve current width/height values
            self.canvas_width.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT}
            self.canvas_height.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT}
        elif isinstance(value, str) and value in CANVAS_DIMENSIONS:
            # 1. If user modifies canvas_size to anything other than custom, get width/height from CANVAS_DIMENSIONS
            self._set_preset_dimensions(value)

    def _enable_custom_dimensions(self, *, publish_updates: bool = True) -> None:
        """Enable custom width and height input fields."""
        canvas_width = self.get_parameter_by_name("width")
        canvas_height = self.get_parameter_by_name("height")
        if canvas_width:
            canvas_width.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT}
        if canvas_height:
            canvas_height.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT}

        if publish_updates:
            self.publish_update_to_parameter("width", self.canvas_width.default_value)
            self.publish_update_to_parameter("height", self.canvas_height.default_value)

    def _set_preset_dimensions(self, value: str) -> None:
        """Set width and height based on preset canvas size."""
        self.canvas_width.allowed_modes = {ParameterMode.OUTPUT}
        self.canvas_height.allowed_modes = {ParameterMode.OUTPUT}

        dimensions = CANVAS_DIMENSIONS[value]
        self.publish_update_to_parameter("width", dimensions["width"])
        self.publish_update_to_parameter("height", dimensions["height"])

    def _handle_input_images_change(self, value: Any) -> None:
        """Handle input_images parameter changes."""
        if value is None or len(value) == 0:
            # All images were removed, clean up the metadata
            self._handle_input_images_removed()
        else:
            # Images were added/removed/reordered, sync metadata
            self._sync_metadata_with_input_images()

    def _handle_bash_image_change(self, value: Any) -> None:  # noqa: ARG002
        """Handle bash_image parameter changes."""
        # Skip during initialization to prevent unwanted syncs
        if self._initializing:
            return

        # Handle bash_image changes (preserve editor state)

        # Don't rebuild konva images when bash_image changes - preserve editor changes
        # Only update output image if it's not a placeholder
        self._update_output_image()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "canvas_size":
            # 1. If user modifies canvas_size to anything other than custom, get width/height from CANVAS_DIMENSIONS
            # 2. If user modifies canvas_size to custom, let them specify width and height
            self._handle_canvas_size_change(value)
        elif parameter.name in ["width", "height", "background_color"] and value is not None:
            # Width, height, and background color parameters are used directly
            pass
        elif "input_images" in parameter.name:
            # 5. If input_images in parameter.name is updated, handle input_image_changes as before
            self._handle_input_images_change(value)
        elif parameter.name == "bash_image" and value is not None:
            # Handle bash_image changes from the editor
            self._handle_bash_image_change(value)

        return super().after_value_set(parameter, value)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle when a connection is removed from a parameter."""
        if "input_images" in target_parameter.name:
            # Get current input_images value after the connection removal
            current_input_images = self.get_parameter_value("input_images") or None
            if current_input_images is None or len(current_input_images) == 0:
                # All images were removed, clean up
                self._handle_input_images_removed()
            else:
                # Some images remain, sync metadata
                self._sync_metadata_with_input_images()
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def _process_output_image(self) -> None:  # noqa: C901, PLR0912, PLR0915
        # Composite the image based on the bash_image meta information
        bash_image = self.get_parameter_value("bash_image")
        if bash_image is None:
            return

        # Extract metadata
        if isinstance(bash_image, dict):
            meta = bash_image.get("meta", {})
        else:
            meta = getattr(bash_image, "meta", {}) or {}

        # Use width and height parameters directly
        canvas_width = self.get_parameter_value("width") or 1920
        canvas_height = self.get_parameter_value("height") or 1080
        if not isinstance(canvas_width, int):
            canvas_width = int(canvas_width)
        if not isinstance(canvas_height, int):
            canvas_height = int(canvas_height)
        background_hex = self.get_parameter_value("background_color") or "#ffffff"

        # Create base canvas
        r, g, b, a = parse_color_to_rgba(background_hex)
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (r, g, b, a))

        # Prepare layer sources
        konva_json = meta.get("konva_json", {}) or {}
        konva_images = konva_json.get("images", []) or []
        input_images = meta.get("input_images", []) or []
        source_id_to_url = {img.get("id"): img.get("url") for img in input_images if isinstance(img, dict)}

        # Sort layers by explicit order, fallback to original order
        indexed_layers = list(enumerate(konva_images))
        indexed_layers.sort(key=lambda pair: pair[1].get("order", pair[0]))

        for _, layer in indexed_layers:
            if not layer.get("visible", True):
                continue

            # Determine source URL: prefer latest mapping from input_images (source_id), fallback to layer src
            src = source_id_to_url.get(layer.get("source_id")) or layer.get("src")
            if not src:
                continue

            # Load image
            try:
                layer_img = load_pil_from_url(src)
            except Exception as e:
                msg = f"{self.name}: Error loading image from {src}: {e}"
                logger.warning(msg)
                continue

            if layer_img.mode != "RGBA":
                layer_img = layer_img.convert("RGBA")

            # Apply scale and base dimensions
            base_w = layer.get("width", layer_img.width) or layer_img.width
            base_h = layer.get("height", layer_img.height) or layer_img.height
            scale_x = float(layer.get("scaleX", 1.0) or 1.0)
            scale_y = float(layer.get("scaleY", 1.0) or 1.0)
            target_w = max(1, round(base_w * scale_x))
            target_h = max(1, round(base_h * scale_y))
            if layer_img.size != (target_w, target_h):
                layer_img = layer_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # Apply rotation (Konva uses degrees; rotate around center)
            rotation = float(layer.get("rotation", 0) or 0)
            if rotation != 0:
                # PIL rotates counter-clockwise for positive angles; negate if needed for Konva's clockwise
                layer_img = layer_img.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)

            # Apply opacity
            try:
                opacity = float(layer.get("opacity", 1) or 1)
            except Exception:
                opacity = 1.0
            if opacity < 1.0:
                alpha = layer_img.getchannel("A")
                alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
                layer_img.putalpha(alpha)

            # Position: Konva x/y represent center
            x = float(layer.get("x", canvas_width / 2))
            y = float(layer.get("y", canvas_height / 2))
            paste_x = round(x - layer_img.width / 2)
            paste_y = round(y - layer_img.height / 2)

            # Paste with alpha mask
            canvas.paste(layer_img, (paste_x, paste_y), layer_img)

        # Save composed image and publish
        filename = self._generate_filename("png")
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(self._pil_to_bytes(canvas, "PNG"), filename)
        output_artifact = ImageUrlArtifact(value=static_url)
        self.set_parameter_value("output_image", output_artifact)
        self.parameter_output_values["output_image"] = output_artifact
        self.publish_update_to_parameter("output_image", output_artifact)
        logger.debug(f"Output image saved to {output_artifact.value}")

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get output filename suffix."""
        return "_image_bash"

    def _generate_filename(self, extension: str) -> str:
        """Generate a meaningful filename based on workflow and node information."""
        # Get processing suffix
        processing_suffix = self._get_output_suffix(
            canvas_size=self.get_parameter_value("canvas_size"),
            width=self.get_parameter_value("width"),
            height=self.get_parameter_value("height"),
            background_color=self.get_parameter_value("background_color"),
        )

        # Use the general filename utility but with a custom prefix
        base_filename = generate_filename(
            node_name=self.name,
            suffix=processing_suffix,
            extension=extension,
        )

        # Add the "image_bash" prefix that this node specifically uses
        return base_filename.replace(f"{self.name}{processing_suffix}", f"image_bash_{self.name}{processing_suffix}")

    def _pil_to_bytes(self, img: Image.Image, img_format: str) -> bytes:
        """Convert PIL Image to bytes."""
        import io

        img_data = None
        with io.BytesIO() as img_byte_arr:
            img.save(img_byte_arr, format=img_format)
            img_byte_arr.seek(0)
            img_data = img_byte_arr.getvalue()

        if img_data is None or len(img_data) == 0:
            msg = f"{self.name}: Failed to convert image to bytes"
            logger.error(msg)
            raise ValueError(msg)

        return img_data

    def _update_output_image(self) -> None:
        bash_image = self.get_parameter_value("bash_image")

        if bash_image is not None:
            # Extract the value from bash_image and create output_image
            if isinstance(bash_image, dict):
                image_value = bash_image.get("value")
            else:
                image_value = bash_image.value

            # Only output if the image value is not a placeholder SVG
            # Placeholder SVGs start with "data:image/svg+xml;base64,"
            if image_value and not image_value.startswith("data:image/svg+xml;base64,"):
                self.set_parameter_value("output_image", ImageUrlArtifact(image_value))
                self.publish_update_to_parameter("output_image", ImageUrlArtifact(image_value))

    def process(self) -> None:
        # comp_on_run: True = compose from metadata; False = pass through editor output
        comp_on_run = self.get_parameter_value("comp_on_run")
        if comp_on_run is None:
            # Backward compatibility: if legacy quick_comp exists, invert its meaning
            legacy_quick = self.get_parameter_value("quick_comp")
            comp_on_run = False if legacy_quick is None else (not bool(legacy_quick))

        if bool(comp_on_run):
            # Ensure bash_image.meta reflects current input_images before composing
            self._sync_metadata_with_input_images()
            self._process_output_image()
        else:
            self._update_output_image()
