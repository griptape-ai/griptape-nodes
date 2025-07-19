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
            # self.add_parameter(self.canvas_size)
            self.canvas_size.add_trait(Options(choices=BASE_CANVAS_OPTIONS))
            self.canvas_width = Parameter(
                name="width",
                default_value=1920,
                input_types=["int"],
                type="int",
                tooltip="The width of the image to create",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"ghost": True},
            )

            self.canvas_height = Parameter(
                name="height",
                default_value=1080,
                input_types=["int"],
                type="int",
                tooltip="The height of the image to create",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"ghost": True},
            )
        # self.add_parameter(self.canvas_width)
        # self.add_parameter(self.canvas_height)
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

        # Create a proper default placeholder SVG
        default_svg = """<svg width="1920" height="1080" xmlns="http://www.w3.org/2000/svg">
  <rect width="1920" height="1080" fill="#fffffa"/>
</svg>"""
        default_svg_base64 = base64.b64encode(default_svg.encode("utf-8")).decode("utf-8")

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
                    "button_icon": "brush",
                    "button_label": "Open Editor",
                    "modal": "PaintBashModal",
                },
                allowed_modes={ParameterMode.PROPERTY},
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

    def _update_bash_image_canvas_size(self) -> None:
        """Update the bash_image metadata with the current canvas dimensions."""
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is None:
            return

        canvas_width, canvas_height = self._get_canvas_dimensions()
        if isinstance(bash_image_value, dict):
            if "meta" not in bash_image_value:
                bash_image_value["meta"] = {}

            # Only update metadata, preserve existing konva_json and background color
            existing_konva = bash_image_value["meta"].get("konva_json", {"images": [], "lines": []})
            existing_background_color = bash_image_value["meta"].get("canvas_background_color", "#ffffff")
            bash_image_value["meta"]["konva_json"] = existing_konva
            bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            bash_image_value["meta"]["canvas_background_color"] = existing_background_color
            bash_image_value["meta"]["viewport"] = {
                "x": 0,
                "y": 0,
                "scale": 1.0,
                "center_x": canvas_width // 2,
                "center_y": canvas_height // 2,
            }
            self.set_parameter_value("bash_image", bash_image_value)
            self.publish_update_to_parameter("bash_image", bash_image_value)
        else:
            meta = getattr(bash_image_value, "meta", {})
            if not isinstance(meta, dict):
                meta = {}

            # Only update metadata, preserve existing konva_json and background color
            existing_konva = meta.get("konva_json", {"images": [], "lines": []})
            existing_background_color = meta.get("canvas_background_color", "#ffffff")
            meta["konva_json"] = existing_konva
            meta["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            meta["canvas_background_color"] = existing_background_color
            meta["viewport"] = {
                "x": 0,
                "y": 0,
                "scale": 1.0,
                "center_x": canvas_width // 2,
                "center_y": canvas_height // 2,
            }
            bash_image_value.meta = meta
            self.set_parameter_value("bash_image", bash_image_value)
            self.publish_update_to_parameter("bash_image", bash_image_value)
            self.parameter_output_values["bash_image"] = bash_image_value

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
        input_images = []
        for i, img in enumerate(current_input_images):
            # Handle different types of input
            if isinstance(img, dict):
                img_artifact = dict_to_image_url_artifact(img)
            elif hasattr(img, "value"):  # ImageArtifact or ImageUrlArtifact
                img_artifact = img
            elif isinstance(img, list):
                # Skip lists - they shouldn't be here
                continue
            else:
                continue

            # Get the image URL
            try:
                image_url = img_artifact.value
            except AttributeError:
                continue

            # Try to preserve existing name, otherwise generate new one
            image_name = None
            for existing_input in existing_input_images:
                if existing_input.get("url") == image_url:
                    image_name = existing_input.get("name")
                    break

            if not image_name:
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

            input_images.append(
                {
                    "id": f"source-img-{i + 1}",
                    "url": image_url,
                    "name": image_name,
                }
            )

        # Build new konva_images array
        konva_images = []

        # First, preserve brush layers (non-input image layers)
        for existing_img in existing_konva.get("images", []):
            existing_type = existing_img.get("type", "")
            existing_id = existing_img.get("id", "")
            existing_source_id = existing_img.get("source_id", "")

            # Check if this is a brush layer
            is_brush_layer = (
                existing_type == "brush"
                or existing_source_id.startswith("brush-")
                or "brush" in existing_source_id.lower()
                or existing_id.startswith("layer-")
            )

            if is_brush_layer:
                konva_images.append(existing_img.copy())

        # Then, create/update konva layers for current input_images
        for i, input_img in enumerate(input_images):
            # Try to find existing konva layer for this image
            existing_konva_img = None
            for existing_img in existing_konva.get("images", []):
                if existing_img.get("source_id") == input_img["id"]:
                    existing_konva_img = existing_img
                    break

            if existing_konva_img:
                # Preserve existing layer data, just update source_id if needed
                konva_img = existing_konva_img.copy()
                konva_img["source_id"] = input_img["id"]
                konva_images.append(konva_img)
            else:
                # Create new layer
                width, height = self._get_image_dimensions(input_img["url"])
                x = canvas_width // 2
                y = canvas_height // 2

                konva_images.append(
                    {
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
                )

        # Update metadata
        if isinstance(bash_image_value, dict):
            if "meta" not in bash_image_value:
                bash_image_value["meta"] = {}

            # Preserve existing background color from metadata
            existing_background_color = existing_meta.get("canvas_background_color", "#ffffff")

            bash_image_value["meta"]["input_images"] = input_images
            bash_image_value["meta"]["konva_json"] = {"images": konva_images, "lines": existing_konva.get("lines", [])}
            bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            bash_image_value["meta"]["canvas_background_color"] = existing_background_color
            bash_image_value["meta"]["viewport"] = {
                "x": 0,
                "y": 0,
                "scale": 1.0,
                "center_x": canvas_width // 2,
                "center_y": canvas_height // 2,
            }
            self.set_parameter_value("bash_image", bash_image_value)
        else:
            # For ImageUrlArtifact
            meta = getattr(bash_image_value, "meta", {})
            if not isinstance(meta, dict):
                meta = {}

            # Preserve existing background color from metadata
            existing_background_color = meta.get("canvas_background_color", "#ffffff")

            meta["input_images"] = input_images
            meta["konva_json"] = {"images": konva_images, "lines": existing_konva.get("lines", [])}
            meta["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            meta["canvas_background_color"] = existing_background_color
            meta["viewport"] = {
                "x": 0,
                "y": 0,
                "scale": 1.0,
                "center_x": canvas_width // 2,
                "center_y": canvas_height // 2,
            }
            bash_image_value.meta = meta
            self.set_parameter_value("bash_image", bash_image_value)

    def _handle_input_images_removed(self) -> None:
        """Handle the case when all input images are removed."""
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is None:
            return

        # Get canvas dimensions
        canvas_width, canvas_height = self._get_canvas_dimensions()

        # Get existing background color from metadata
        existing_background_color = "#ffffff"
        if isinstance(bash_image_value, dict):
            existing_background_color = bash_image_value.get("meta", {}).get("canvas_background_color", "#ffffff")
        else:
            existing_background_color = getattr(bash_image_value, "meta", {}).get("canvas_background_color", "#ffffff")

        # Create new placeholder with existing background color
        svg_content = f"""<svg width="{canvas_width}" height="{canvas_height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{canvas_width}" height="{canvas_height}" fill="{existing_background_color}"/>
</svg>"""
        new_placeholder_url = (
            f"data:image/svg+xml;base64,{base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')}"
        )

        if isinstance(bash_image_value, dict):
            if "meta" not in bash_image_value:
                bash_image_value["meta"] = {}

            # Clear input_images and konva images, but preserve brush layers
            existing_konva = bash_image_value["meta"].get("konva_json", {"images": [], "lines": []})

            # Keep only brush layers (remove image layers)
            brush_layers = []
            for img in existing_konva.get("images", []):
                existing_type = img.get("type", "")
                existing_id = img.get("id", "")
                existing_source_id = img.get("source_id", "")

                # Check if this is a brush layer
                is_brush_layer = (
                    existing_type == "brush"
                    or existing_source_id.startswith("brush-")
                    or "brush" in existing_source_id.lower()
                    or existing_id.startswith("layer-")
                )

                if is_brush_layer:
                    brush_layers.append(img.copy())

            # Update metadata
            bash_image_value["value"] = new_placeholder_url
            bash_image_value["meta"]["input_images"] = []
            bash_image_value["meta"]["konva_json"] = {"images": brush_layers, "lines": existing_konva.get("lines", [])}
            bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            bash_image_value["meta"]["canvas_background_color"] = existing_background_color
            bash_image_value["meta"]["viewport"] = {
                "x": 0,
                "y": 0,
                "scale": 1.0,
                "center_x": canvas_width // 2,
                "center_y": canvas_height // 2,
            }
            self.set_parameter_value("bash_image", bash_image_value)
        else:
            # For ImageUrlArtifact, update its metadata
            meta = getattr(bash_image_value, "meta", {})
            if not isinstance(meta, dict):
                meta = {}

            # Clear input_images and konva images, but preserve brush layers
            existing_konva = meta.get("konva_json", {"images": [], "lines": []})

            # Keep only brush layers (remove image layers)
            brush_layers = []
            for img in existing_konva.get("images", []):
                existing_type = img.get("type", "")
                existing_id = img.get("id", "")
                existing_source_id = img.get("source_id", "")

                # Check if this is a brush layer
                is_brush_layer = (
                    existing_type == "brush"
                    or existing_source_id.startswith("brush-")
                    or "brush" in existing_source_id.lower()
                    or existing_id.startswith("layer-")
                )

                if is_brush_layer:
                    brush_layers.append(img.copy())

            # Update metadata
            bash_image_value.value = new_placeholder_url
            meta["input_images"] = []
            meta["konva_json"] = {"images": brush_layers, "lines": existing_konva.get("lines", [])}
            meta["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            meta["canvas_background_color"] = existing_background_color
            meta["viewport"] = {
                "x": 0,
                "y": 0,
                "scale": 1.0,
                "center_x": canvas_width // 2,
                "center_y": canvas_height // 2,
            }
            bash_image_value.meta = meta
            self.set_parameter_value("bash_image", bash_image_value)

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

            # Get the image name from the artifact, fallback to filename from URL, then to generic name
            image_name = getattr(img_artifact, "name", None)
            if not image_name:
                # Try to extract filename from URL
                try:
                    from urllib.parse import urlparse

                    parsed_url = urlparse(img_artifact.value)
                    filename = parsed_url.path.split("/")[-1]
                    if filename and "." in filename:
                        image_name = filename.split(".")[0]  # Remove extension
                    else:
                        image_name = f"Image {i + 1}"
                except:
                    image_name = f"Image {i + 1}"

            input_images.append({"id": f"source-img-{i + 1}", "url": img_artifact.value, "name": image_name})

        # Get canvas dimensions from parameters
        canvas_width, canvas_height = self._get_canvas_dimensions()
        canvas_background_color = "#ffffff"  # Default background color

        # Create basic Konva JSON structure with image elements
        konva_images = []

        for i, input_img in enumerate(input_images):
            # Get actual image dimensions
            width, height = self._get_image_dimensions(input_img["url"])

            # Center the image on the canvas
            x = canvas_width // 2
            y = canvas_height // 2

            konva_images.append(
                {
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
            )

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
                    "viewport": {
                        "x": 0,
                        "y": 0,
                        "scale": 1.0,
                        "center_x": canvas_width // 2,
                        "center_y": canvas_height // 2,
                    },
                },
            }
        )
        self.set_parameter_value("bash_image", bash_image_artifact)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "canvas_size":
            if value == "custom":
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
            elif isinstance(value, str) and value in CANVAS_DIMENSIONS:
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

            # Update bash_image canvas size when canvas_size changes
            self._update_bash_image_canvas_size()

        # Update bash image when width or height changes
        elif parameter.name in ["width", "height"] and value is not None:
            # Update bash_image canvas size when width/height changes
            self._update_bash_image_canvas_size()

        if "input_images" in parameter.name:
            # When input_images changes, sync the metadata
            if value is None or len(value) == 0:
                # All images were removed, clean up the metadata
                self._handle_input_images_removed()
            else:
                # Images were added/removed/reordered, sync metadata
                self._sync_metadata_with_input_images()

        if parameter.name == "bash_image" and value is not None:
            # Check if canvas dimensions have changed in the metadata
            if isinstance(value, dict):
                meta = value.get("meta", {})
            else:
                meta = getattr(value, "meta", {})

            canvas_size_meta = meta.get("canvas_size", {})
            metadata_width = canvas_size_meta.get("width")
            metadata_height = canvas_size_meta.get("height")
            if metadata_width and metadata_height:
                # Get current canvas dimensions from parameters
                current_width, current_height = self._get_canvas_dimensions()

                if metadata_width != current_width or metadata_height != current_height:
                    # Set canvas_size to custom
                    self.set_parameter_value("canvas_size", "custom")

                    # Update width and height parameters
                    self.set_parameter_value("width", metadata_width)
                    self.set_parameter_value("height", metadata_height)

                    # publish the changes
                    self.publish_update_to_parameter("canvas_size", "custom")
                    self.publish_update_to_parameter("width", metadata_width)
                    self.publish_update_to_parameter("height", metadata_height)
                # Initialize bash_image metadata with current parameters if it's still using default values
            self._update_output_image()
        if parameter.name == "canvas_size" and value is not None:
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
                bash_image_value["meta"]["viewport"] = {
                    "x": 0,
                    "y": 0,
                    "scale": 1.0,
                    "center_x": canvas_width // 2,
                    "center_y": canvas_height // 2,
                }
                self.set_parameter_value("bash_image", bash_image_value)

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
