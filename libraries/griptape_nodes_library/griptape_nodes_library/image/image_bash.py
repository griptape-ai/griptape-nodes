import base64
from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact, JsonArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact

CANVAS_DIMENSIONS = {
    "HD": {"width": 1920, "height": 1080},  # 16:9 HD
    "2K": {"width": 2560, "height": 1440},  # 16:9 2K
    "4K": {"width": 3840, "height": 2160},  # 16:9 4K
    "A4": {"width": 2480, "height": 3508},  # A4 at 300dpi
    "A3": {"width": 3508, "height": 4961},  # A3 at 300dpi
    "square": {"width": 2000, "height": 2000},  # Square format
    "landscape": {"width": 2000, "height": 1500},  # 4:3 landscape
    "portrait": {"width": 1500, "height": 2000},  # 3:4 portrait
    "custom": {"width": 1920, "height": 1080},  # Default custom size
}
BASE_CANVAS_OPTIONS = [*list(CANVAS_DIMENSIONS.keys())]

default_svg = """<svg width="1920" height="1080" xmlns="http://www.w3.org/2000/svg">
<rect width="1920" height="1080" fill="#fffffa"/>
</svg>"""
default_svg_base64 = base64.b64encode(default_svg.encode("utf-8")).decode("utf-8")


class ImageBash(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        with ParameterGroup(name="canvas_details", ui_options={"collapsed": True}) as canvas_details_group:
            self.canvas_size = Parameter(
                name="canvas_size",
                default_value=BASE_CANVAS_OPTIONS[0],
                type="string",
                tooltip="The size of the canvas to create",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            self.canvas_size.add_trait(Options(choices=BASE_CANVAS_OPTIONS))
            self.canvas_width = Parameter(
                name="width",
                default_value=CANVAS_DIMENSIONS[BASE_CANVAS_OPTIONS[0]]["width"],
                input_types=["int"],
                type="int",
                tooltip="The width of the image to create",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"ghost": True},
            )

            self.canvas_height = Parameter(
                name="height",
                default_value=CANVAS_DIMENSIONS[BASE_CANVAS_OPTIONS[0]]["height"],
                input_types=["int"],
                type="int",
                tooltip="The height of the image to create",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"ghost": True},
            )
        self.add_node_element(canvas_details_group)

        self.add_parameter(
            ParameterList(
                name="input_images",
                default_value=[],
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
                        "canvas_size": {"width": 1920, "height": 1080},
                        "canvas_background_color": "#fffffa",
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
            width = self.get_parameter_value("width") or CANVAS_DIMENSIONS["custom"]["width"]
            height = self.get_parameter_value("height") or CANVAS_DIMENSIONS["custom"]["height"]
            return (width, height)
        if canvas_size in CANVAS_DIMENSIONS:
            dimensions = CANVAS_DIMENSIONS[canvas_size]
            return (dimensions["width"], dimensions["height"])
        # Fallback to HD
        dimensions = CANVAS_DIMENSIONS["HD"]
        return (dimensions["width"], dimensions["height"])

    def _get_existing_background_color(self, bash_image_value: Any) -> str:
        """Get the existing background color from bash_image metadata."""
        if isinstance(bash_image_value, dict):
            return bash_image_value.get("meta", {}).get("canvas_background_color", "#ffffff")
        return getattr(bash_image_value, "meta", {}).get("canvas_background_color", "#ffffff")

    def _create_viewport_metadata(self, canvas_width: int, canvas_height: int) -> dict:
        """Create viewport metadata for the given canvas dimensions."""
        return {
            "x": 0,
            "y": 0,
            "scale": 1.0,
            "center_x": canvas_width // 2,
            "center_y": canvas_height // 2,
        }

    def _update_bash_image_canvas_size(self) -> None:
        """Update the bash_image metadata with the current canvas dimensions."""
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is None:
            return

        canvas_width, canvas_height = self._get_canvas_dimensions()
        existing_background_color = self._get_existing_background_color(bash_image_value)

        # Use the common metadata update method
        self._update_bash_image_metadata(
            bash_image_value,
            [],  # Don't change input_images
            [],  # Don't change konva_images
            {"images": [], "lines": []},  # Don't change existing_konva
            canvas_width,
            canvas_height,
            existing_background_color,
            preserve_existing=True,
        )

    def _update_bash_image_metadata(  # noqa: PLR0913
        self,
        bash_image_value: Any,
        input_images: list,
        konva_images: list,
        existing_konva: dict,
        canvas_width: int,
        canvas_height: int,
        existing_background_color: str,
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

            bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            bash_image_value["meta"]["canvas_background_color"] = existing_background_color
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

            meta["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            meta["canvas_background_color"] = existing_background_color
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
        image_name = self._get_image_name(img_artifact, image_url, i, existing_input_images)

        return {
            "id": f"source-img-{i + 1}",
            "url": image_url,
            "name": image_name,
        }

    def _get_image_name(self, img_artifact: Any, image_url: str, i: int, existing_input_images: list) -> str:
        """Get or generate a name for an image."""
        # Try to preserve existing name
        for existing_input in existing_input_images:
            if existing_input.get("url") == image_url:
                return existing_input.get("name")

        # Generate new name
        image_name = getattr(img_artifact, "name", None)
        if not image_name:
            try:
                from urllib.parse import urlparse

                parsed_url = urlparse(image_url)
                filename = parsed_url.path.split("/")[-1]
                if filename and "." in filename:
                    image_name = filename.split(".")[0]
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

    def _create_konva_layer(self, input_img: dict, i: int, canvas_width: int, canvas_height: int) -> dict:
        """Create a new konva layer for an input image."""
        width, height = self._get_image_dimensions(input_img["url"])
        x = canvas_width // 2
        y = canvas_height // 2

        return {
            "id": f"canvas-img-{i + 1}",
            "source_id": input_img["id"],
            "src": input_img["url"],
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "rotation": 0,
            "scaleX": 1.0,
            "scaleY": 1.0,
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

        # Preserve existing background color from metadata
        existing_background_color = existing_meta.get("canvas_background_color", "#ffffff")

        # Update metadata
        self._update_bash_image_metadata(
            bash_image_value,
            input_images,
            konva_images,
            existing_konva,
            canvas_width,
            canvas_height,
            existing_background_color,
        )

    def _handle_input_images_removed(self) -> None:
        """Handle the case when all input images are removed."""
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is None:
            return

        # Get canvas dimensions
        canvas_width, canvas_height = self._get_canvas_dimensions()
        existing_background_color = self._get_existing_background_color(bash_image_value)

        # Create new placeholder with existing background color
        svg_content = f"""<svg width="{canvas_width}" height="{canvas_height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{canvas_width}" height="{canvas_height}" fill="{existing_background_color}"/>
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
            existing_background_color,
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
            image_name = self._get_image_name(img_artifact, img_artifact.value, i, [])
            input_images.append({"id": f"source-img-{i + 1}", "url": img_artifact.value, "name": image_name})

        # Get canvas dimensions from parameters
        canvas_width, canvas_height = self._get_canvas_dimensions()
        canvas_background_color = "#ffffff"  # Default background color

        # Create basic Konva JSON structure with image elements using existing helper
        konva_images = [
            self._create_konva_layer(input_img, i, canvas_width, canvas_height)
            for i, input_img in enumerate(input_images)
        ]

        konva_json = {"images": konva_images, "lines": []}

        # Use a simple placeholder URL - the actual canvas is defined by canvas_size and konva_json
        svg_content = f"""<svg width="{canvas_width}" height="{canvas_height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{canvas_width}" height="{canvas_height}" fill="{canvas_background_color}"/>
</svg>"""
        placeholder_url = f"data:image/svg+xml;base64,{base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')}"

        bash_image_artifact = JsonArtifact(
            {
                "value": placeholder_url,
                "name": "Canvas Project",
                "meta": {
                    "input_images": input_images,
                    "konva_json": konva_json,
                    "canvas_size": {"width": canvas_width, "height": canvas_height},
                    "canvas_background_color": canvas_background_color,
                    "viewport": self._create_viewport_metadata(canvas_width, canvas_height),
                },
            }
        )
        self.set_parameter_value("bash_image", bash_image_artifact)

    def _handle_canvas_size_change(self, value: Any) -> None:
        """Handle canvas_size parameter changes."""
        if value == "custom":
            # 2. If user modifies canvas_size to custom, let them specify width and height
            self._enable_custom_dimensions()
        elif isinstance(value, str) and value in CANVAS_DIMENSIONS:
            # 1. If user modifies canvas_size to anything other than custom, get width/height from CANVAS_DIMENSIONS
            self._set_preset_dimensions(value)

        # Update bash_image canvas size when canvas_size changes
        self._update_bash_image_canvas_size()

    def _enable_custom_dimensions(self) -> None:
        """Enable custom width and height input fields."""
        width_ui_options = self.canvas_width.ui_options
        self.canvas_width.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}
        width_ui_options["ghost"] = False
        self.canvas_width.ui_options = width_ui_options

        height_ui_options = self.canvas_height.ui_options
        self.canvas_height.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}
        height_ui_options["ghost"] = False
        self.canvas_height.ui_options = height_ui_options

        self.publish_update_to_parameter("width", self.canvas_width.default_value)
        self.publish_update_to_parameter("height", self.canvas_height.default_value)

    def _set_preset_dimensions(self, value: str) -> None:
        """Set width and height based on preset canvas size."""
        width_ui_options = self.canvas_width.ui_options
        self.canvas_width.allowed_modes = {ParameterMode.PROPERTY}
        width_ui_options["ghost"] = True
        self.canvas_width.ui_options = width_ui_options

        height_ui_options = self.canvas_height.ui_options
        self.canvas_height.allowed_modes = {ParameterMode.PROPERTY}
        height_ui_options["ghost"] = True
        self.canvas_height.ui_options = height_ui_options

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

    def _handle_bash_image_change(self, value: Any) -> None:
        """Handle bash_image parameter changes."""
        # Only sync canvas dimensions if the bash_image is being initialized for the first time
        # or if there's a significant mismatch that needs to be resolved
        if isinstance(value, dict):
            meta = value.get("meta", {})
        else:
            meta = getattr(value, "meta", {})

        canvas_size_meta = meta.get("canvas_size", {})
        metadata_width = canvas_size_meta.get("width")
        metadata_height = canvas_size_meta.get("height")

        # Only sync if we have metadata dimensions and they're significantly different from current parameters
        if metadata_width and metadata_height:
            current_width, current_height = self._get_canvas_dimensions()
            # Only sync if there's a significant difference (more than 1 pixel)
            if abs(metadata_width - current_width) > 1 or abs(metadata_height - current_height) > 1:
                self._sync_canvas_dimensions_from_metadata(metadata_width, metadata_height)

        # Don't rebuild konva images when bash_image changes - preserve editor changes
        # Only update output image if it's not a placeholder
        self._update_output_image()

    def _sync_canvas_dimensions_from_metadata(self, metadata_width: int, metadata_height: int) -> None:
        """Sync canvas dimensions from metadata to parameters."""
        # Get current canvas dimensions from parameters
        current_width, current_height = self._get_canvas_dimensions()

        if metadata_width != current_width or metadata_height != current_height:
            # Set canvas_size to custom and enable custom dimensions
            self.set_parameter_value("canvas_size", "custom")
            self._enable_custom_dimensions()

            # Update width and height parameters
            self.set_parameter_value("width", metadata_width)
            self.set_parameter_value("height", metadata_height)

            # publish the changes
            self.publish_update_to_parameter("canvas_size", "custom")
            self.publish_update_to_parameter("width", metadata_width)
            self.publish_update_to_parameter("height", metadata_height)

    def _update_canvas_size_metadata(self, value: Any) -> None:
        """Update canvas size metadata when canvas_size changes."""
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is not None and isinstance(bash_image_value, dict):
            # Only update metadata, don't replace the bash_image value
            canvas_width, canvas_height = self._get_canvas_dimensions()

            if "meta" not in bash_image_value:
                bash_image_value["meta"] = {}

            # Preserve existing background color
            existing_background_color = bash_image_value["meta"].get("canvas_background_color", "#ffffff")

            bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            bash_image_value["meta"]["canvas_background_color"] = existing_background_color
            bash_image_value["meta"]["viewport"] = self._create_viewport_metadata(canvas_width, canvas_height)
            self.set_parameter_value("bash_image", bash_image_value)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "canvas_size":
            # 1. If user modifies canvas_size to anything other than custom, get width/height from CANVAS_DIMENSIONS
            # 2. If user modifies canvas_size to custom, let them specify width and height
            self._handle_canvas_size_change(value)
        elif parameter.name in ["width", "height"] and value is not None:
            # 3. If width and height are changed - update the bash_image.meta value to have the appropriate canvas size width and height
            self._update_bash_image_canvas_size()
        elif "input_images" in parameter.name:
            # 5. If input_images in parameter.name is updated, handle input_image_changes as before
            self._handle_input_images_change(value)
        elif parameter.name == "bash_image" and value is not None:
            # 4. If bash_image.meta width and height changes from an external process,
            # make sure the canvas_size is CUSTOM and set width and height from the bash_image.meta
            self._handle_bash_image_change(value)

        return super().after_value_set(parameter, value)

    def after_incoming_connection_removed(self, parameter: Parameter) -> None:
        """Handle when a connection is removed from a parameter."""
        if "input_images" in parameter.name:
            # Get current input_images value after the connection removal
            current_input_images = self.get_parameter_value("input_images") or []

            if len(current_input_images) == 0:
                # All images were removed, clean up
                self._handle_input_images_removed()
            else:
                # Some images remain, sync metadata
                self._sync_metadata_with_input_images()

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
        self._update_output_image()
