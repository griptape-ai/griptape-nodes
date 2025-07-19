import base64
from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger
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

        self.canvas_size = Parameter(
            name="canvas_size",
            default_value=BASE_CANVAS_OPTIONS[0],
            type="string",
            tooltip="The size of the canvas to create",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.canvas_size)
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
        self.add_parameter(self.canvas_width)
        self.add_parameter(self.canvas_height)

        self.canvas_background_color = Parameter(
            name="canvas_background_color",
            default_value="#ffffff",
            type="string",
            tooltip="The background color of the canvas (supports hex, rgb, hsv, etc.)",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.canvas_background_color)

        self.add_parameter(
            ParameterList(
                name="input_images",
                default_value=[],
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="The images to use for the image",
                ui_options={"expander": True, "edit_images": True},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Create a proper default placeholder SVG
        default_svg = """<svg width="1920" height="1080" xmlns="http://www.w3.org/2000/svg">
  <rect width="1920" height="1080" fill="#ffffff"/>
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
                        "canvas_background_color": "#ffffff",
                        "input_images": [],
                        "konva_json": {"images": [], "lines": []},
                        "viewport": {"x": 0, "y": 0, "scale": 1.0, "center_x": 960, "center_y": 540},
                    },
                },
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="The excalidraw image to use for the image",
                ui_options={"expander": True, "edit_excalidraw": True},
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
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

    def _parse_color_to_rgb(self, color_str: str) -> tuple[int, int, int, int]:
        """Parse color string to RGB values with alpha channel."""
        import re

        # Default to white with full opacity
        if not color_str:
            return (255, 255, 255, 255)

        color_str = color_str.strip().lower()

        # Handle hex colors (#ffffff, #fff)
        if color_str.startswith("#"):
            hex_color = color_str[1:]
            if len(hex_color) == 3:
                # Expand 3-digit hex to 6-digit
                hex_color = "".join([c + c for c in hex_color])
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return (r, g, b, 255)

        # Handle rgb(r, g, b) format
        rgb_match = re.match(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", color_str)
        if rgb_match:
            r = int(rgb_match.group(1))
            g = int(rgb_match.group(2))
            b = int(rgb_match.group(3))
            return (r, g, b, 255)

        # Handle rgba(r, g, b, a) format
        rgba_match = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", color_str)
        if rgba_match:
            r = int(rgba_match.group(1))
            g = int(rgba_match.group(2))
            b = int(rgba_match.group(3))
            a = int(float(rgba_match.group(4)) * 255)
            return (r, g, b, a)

        # Handle named colors (basic support)
        named_colors = {
            "white": (255, 255, 255, 255),
            "black": (0, 0, 0, 255),
            "red": (255, 0, 0, 255),
            "green": (0, 255, 0, 255),
            "blue": (0, 0, 255, 255),
            "yellow": (255, 255, 0, 255),
            "cyan": (0, 255, 255, 255),
            "magenta": (255, 0, 255, 255),
            "gray": (128, 128, 128, 255),
            "grey": (128, 128, 128, 255),
            "transparent": (255, 255, 255, 0),
        }

        if color_str in named_colors:
            return named_colors[color_str]

        # Fallback to white
        logger.info(f"⚠️  Unknown color format: {color_str}, using white")
        return (255, 255, 255, 255)

    def _create_placeholder_svg_base64(self, width: int, height: int, background_color: str) -> str:
        """Create a base64-encoded SVG placeholder with the specified dimensions and background color."""
        logger.info(f"🎨 Creating placeholder SVG: {width}x{height} with color {background_color}")

        # Convert color to hex for SVG
        r, g, b, a = self._parse_color_to_rgb(background_color)
        hex_color = f"#{r:02x}{g:02x}{b:02x}"

        logger.info(f"🎨 Parsed color {background_color} to RGB({r},{g},{b}) -> hex {hex_color}")

        # Create SVG with the specified dimensions and background color
        svg_content = f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="{hex_color}"/>
</svg>"""

        # Encode to base64
        return base64.b64encode(svg_content.encode("utf-8")).decode("utf-8")

    def _composite_layers_to_image(self, bash_image_value: Any) -> ImageUrlArtifact | None:
        """Composite all layers into a final image based on their transformations."""
        if bash_image_value is None:
            return None

        # Get metadata
        if isinstance(bash_image_value, dict):
            meta = bash_image_value.get("meta", {})
        else:
            meta = getattr(bash_image_value, "meta", {})

        konva_json = meta.get("konva_json", {})
        canvas_size = meta.get("canvas_size", {})

        if not canvas_size or not konva_json:
            return None

        canvas_width = canvas_size.get("width", 1920)
        canvas_height = canvas_size.get("height", 1080)
        canvas_background_color = meta.get("canvas_background_color", "#ffffff")
        layers = konva_json.get("images", [])
        input_images = meta.get("input_images", [])

        logger.info(f"🎨 Compositing with background color: {canvas_background_color}")
        logger.info(f"🎨 Found {len(layers)} konva layers and {len(input_images)} input images")

        if not layers:
            logger.info("📭 No layers to composite, creating background-only image")
            # Create a background-only image
            background_rgb = self._parse_color_to_rgb(canvas_background_color)
            canvas = Image.new("RGBA", (canvas_width, canvas_height), background_rgb)

            # Save to bytes
            output_buffer = BytesIO()
            canvas.save(output_buffer, format="PNG")
            output_buffer.seek(0)

            # Create data URL
            image_data = base64.b64encode(output_buffer.getvalue()).decode("utf-8")
            data_url = f"data:image/png;base64,{image_data}"

            return ImageUrlArtifact(data_url)

        print(
            f"🎨 Compositing {len(layers)} layers on canvas {canvas_width}x{canvas_height} with background {canvas_background_color}"
        )

        # Create base canvas with background color
        # Convert color string to RGB values
        background_rgb = self._parse_color_to_rgb(canvas_background_color)
        canvas = Image.new("RGBA", (canvas_width, canvas_height), background_rgb)

        # Create a mapping of source_id to input_image for quick lookup
        input_image_map = {img["id"]: img for img in input_images}

        # Process layers in order (bottom to top)
        for layer in layers:
            layer_id = layer.get("id", "unknown")
            layer_type = layer.get("type", "unknown")
            layer_visible = layer.get("visible", True)
            layer_src = layer.get("src")
            source_id = layer.get("source_id")

            print(
                f"🔍 Examining layer: {layer_id} (type: {layer_type}, visible: {layer_visible}, source_id: {source_id})"
            )

            if not layer_visible:
                print(f"⏭️  Skipping invisible layer: {layer_id}")
                continue

            # Try to get the image URL from input_images metadata first
            image_url = None
            if source_id and source_id in input_image_map:
                image_url = input_image_map[source_id]["url"]
                print(f"📋 Found image URL from metadata: {image_url}")
            elif layer_src:
                image_url = layer_src
                print(f"🔗 Using layer src: {image_url}")
            else:
                print(f"⚠️  Layer {layer_id} has no src or source_id")
                continue

            try:
                # Load the layer image
                if image_url.startswith("data:"):
                    # Handle data URLs
                    header, data = image_url.split(",", 1)
                    if "base64" in header:
                        image_data = base64.b64decode(data)
                        layer_img = Image.open(BytesIO(image_data)).convert("RGBA")
                    else:
                        continue
                else:
                    # Handle regular URLs (including brush layers converted to images)
                    response = httpx.get(image_url, timeout=30)
                    response.raise_for_status()
                    layer_img = Image.open(BytesIO(response.content)).convert("RGBA")

                # Get layer properties
                x = layer.get("x", 0)
                y = layer.get("y", 0)
                width = layer.get("width", layer_img.width)
                height = layer.get("height", layer_img.height)
                rotation = layer.get("rotation", 0)
                scale_x = layer.get("scaleX", 1.0)
                scale_y = layer.get("scaleY", 1.0)
                opacity = layer.get("opacity", 1.0)

                # Resize image if needed
                if width != layer_img.width or height != layer_img.height:
                    layer_img = layer_img.resize((int(width), int(height)), Image.Resampling.LANCZOS)

                # Apply scaling
                if scale_x != 1.0 or scale_y != 1.0:
                    new_width = int(width * scale_x)
                    new_height = int(height * scale_y)
                    layer_img = layer_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    width, height = new_width, new_height

                # Apply rotation
                if rotation != 0:
                    layer_img = layer_img.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

                # Apply opacity
                if opacity != 1.0:
                    # Create a new image with adjusted alpha
                    alpha = layer_img.split()[3]
                    alpha = alpha.point(lambda x: int(x * opacity))
                    layer_img.putalpha(alpha)

                # Calculate position (center the image at x, y)
                img_width, img_height = layer_img.size
                paste_x = int(x - img_width // 2)
                paste_y = int(y - img_height // 2)

                # Paste the layer onto the canvas
                canvas.paste(layer_img, (paste_x, paste_y), layer_img)

            except Exception as e:
                # Skip layers that fail to load
                print(f"Failed to composite layer {layer.get('id', 'unknown')}: {e}")
                continue

        # Convert to RGB if no transparency needed
        if canvas.mode == "RGBA":
            # Check if there's any transparency
            alpha = canvas.split()[3]
            if alpha.getextrema()[1] == 255:
                canvas = canvas.convert("RGB")

        # Save to bytes
        output_buffer = BytesIO()
        canvas.save(output_buffer, format="PNG")
        output_buffer.seek(0)

        # Create data URL
        image_data = base64.b64encode(output_buffer.getvalue()).decode("utf-8")
        data_url = f"data:image/png;base64,{image_data}"

        return ImageUrlArtifact(data_url)

    def _create_clean_output_image(self, bash_image_value: Any) -> ImageUrlArtifact | None:
        """Create a clean output image without konva_json metadata."""
        if bash_image_value is None:
            return None

        if isinstance(bash_image_value, dict):
            # Create clean metadata without konva_json
            clean_meta = {}
            if "meta" in bash_image_value:
                original_meta = bash_image_value["meta"]
                for key, value in original_meta.items():
                    if key != "konva_json":
                        clean_meta[key] = value

            return ImageUrlArtifact(bash_image_value["value"], meta=clean_meta)
        # For ImageUrlArtifact, create new one without konva_json
        original_meta = getattr(bash_image_value, "meta", {})
        clean_meta = {}

        if isinstance(original_meta, dict):
            for key, value in original_meta.items():
                if key != "konva_json":
                    clean_meta[key] = value

        return ImageUrlArtifact(bash_image_value.value, meta=clean_meta)

    def _update_bash_image_canvas_size(self) -> None:
        """Update the bash_image metadata with the current canvas dimensions."""
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is None:
            return

        canvas_width, canvas_height = self._get_canvas_dimensions()
        canvas_background_color = self.get_parameter_value("canvas_background_color") or "#ffffff"

        if isinstance(bash_image_value, dict):
            if "meta" not in bash_image_value:
                bash_image_value["meta"] = {}

            # Update konva_json with new canvas dimensions
            konva_json = bash_image_value["meta"].get("konva_json", {"images": [], "lines": []})

            bash_image_value["meta"]["konva_json"] = konva_json
            bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            bash_image_value["meta"]["canvas_background_color"] = canvas_background_color
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

            # Update konva_json with new canvas dimensions
            konva_json = meta.get("konva_json", {"images": [], "lines": []})

            meta["konva_json"] = konva_json
            meta["canvas_size"] = {"width": canvas_width, "height": canvas_height}
            meta["canvas_background_color"] = canvas_background_color
            meta["viewport"] = {
                "x": 0,
                "y": 0,
                "scale": 1.0,
                "center_x": canvas_width // 2,
                "center_y": canvas_height // 2,
            }
            bash_image_value.meta = meta
            self.set_parameter_value("bash_image", bash_image_value)

    def _handle_input_image_change(self, value: Any) -> None:
        # Check and see if the bash_image is set
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is None:
            self._create_new_bash_image()
        else:
            # Get the list of images from the ParameterList
            images_list = self.get_parameter_value("input_images") or []

            # Get existing metadata to preserve names and konva data
            existing_meta = {}
            if isinstance(bash_image_value, dict):
                existing_meta = bash_image_value.get("meta", {})
            else:
                existing_meta = getattr(bash_image_value, "meta", {})

            existing_input_images = existing_meta.get("input_images", [])
            existing_konva = existing_meta.get("konva_json", {"images": [], "lines": []})

            # Create updated input_images array, preserving existing names and metadata
            input_images = []
            for i, img in enumerate(images_list):
                if isinstance(img, dict):
                    img_artifact = dict_to_image_url_artifact(img)
                else:
                    img_artifact = img

                # Try to find existing metadata for this image
                existing_image = None
                if i < len(existing_input_images):
                    existing_image = existing_input_images[i]

                # Use existing name if available, otherwise generate new one
                if existing_image and "name" in existing_image:
                    image_name = existing_image["name"]
                else:
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

                input_images.append(
                    {
                        "id": f"source-img-{i + 1}",
                        "url": img_artifact.value,  # Always update URL
                        "name": image_name,
                    }
                )

            # Update konva images, preserving existing positions and transformations
            konva_images = []

            # Get canvas dimensions from parameters
            canvas_width, canvas_height = self._get_canvas_dimensions()
            canvas_background_color = self.get_parameter_value("canvas_background_color") or "#ffffff"

            logger.info(
                f"🔄 Updating konva_json - existing images: {len(existing_konva.get('images', []))}, existing lines: {len(existing_konva.get('lines', []))}"
            )

            # Debug: show what's in existing images
            for i, img in enumerate(existing_konva.get("images", [])):
                logger.info(
                    f"  Existing image {i}: id={img.get('id')}, source_id={img.get('source_id')}, type={img.get('type', 'unknown')}"
                )

            # Debug: show what's in existing lines
            for i, line in enumerate(existing_konva.get("lines", [])):
                logger.info(f"  Existing line {i}: id={line.get('id')}, type={line.get('type', 'unknown')}")

            for i, input_img in enumerate(input_images):
                # Try to find existing konva image data
                existing_konva_img = None
                for img in existing_konva.get("images", []):
                    if img.get("source_id") == f"source-img-{i + 1}":
                        existing_konva_img = img
                        break

                if existing_konva_img:
                    # Preserve existing konva data, just update source_id if needed
                    konva_img = existing_konva_img.copy()
                    konva_img["source_id"] = input_img["id"]
                    konva_images.append(konva_img)
                else:
                    # Create new konva image with centered positioning
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

            # Preserve brush layers that might not be in input_images
            # Brush layers might have different source_id patterns or be stored differently
            for existing_img in existing_konva.get("images", []):
                existing_source_id = existing_img.get("source_id", "")
                existing_type = existing_img.get("type", "")
                existing_id = existing_img.get("id", "")

                # Check if this is a brush layer (not a regular input image)
                is_brush_layer = (
                    existing_type == "brush"
                    or existing_source_id.startswith("brush-")
                    or "brush" in existing_source_id.lower()
                    or existing_id.startswith("layer-")  # Brush layers have layer- IDs
                )

                if is_brush_layer:
                    # Check if this brush layer is already in our konva_images list
                    already_preserved = any(
                        img.get("id") == existing_id or img.get("source_id") == existing_source_id
                        for img in konva_images
                    )

                    if not already_preserved:
                        # Preserve brush layers
                        logger.info(f"🖌️ Preserving brush layer: {existing_id} (type: {existing_type})")
                        konva_images.append(existing_img.copy())

            # If bash_image is a dict, update its metadata
            if isinstance(bash_image_value, dict):
                if "meta" not in bash_image_value:
                    bash_image_value["meta"] = {}

                # Update konva_json while preserving lines
                existing_konva["images"] = konva_images

                bash_image_value["meta"]["input_images"] = input_images
                bash_image_value["meta"]["konva_json"] = existing_konva
                bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
                bash_image_value["meta"]["canvas_background_color"] = canvas_background_color
                bash_image_value["meta"]["viewport"] = {
                    "x": 0,
                    "y": 0,
                    "scale": 1.0,
                    "center_x": canvas_width // 2,
                    "center_y": canvas_height // 2,
                }
                self.set_parameter_value("bash_image", bash_image_value)

                logger.info(
                    f"✅ Updated konva_json - final images: {len(existing_konva.get('images', []))}, final lines: {len(existing_konva.get('lines', []))}"
                )
            else:
                # For ImageUrlArtifact, update its metadata
                meta = getattr(bash_image_value, "meta", {})
                if not isinstance(meta, dict):
                    meta = {}

                # Update konva_json while preserving lines
                existing_konva["images"] = konva_images

                meta["input_images"] = input_images
                meta["konva_json"] = existing_konva
                meta["canvas_size"] = {"width": canvas_width, "height": canvas_height}
                meta["canvas_background_color"] = canvas_background_color
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
        logger.info("🆕 Creating new bash image...")

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
        canvas_background_color = self.get_parameter_value("canvas_background_color") or "#ffffff"

        logger.info(f"🎨 Canvas dimensions: {canvas_width}x{canvas_height}, background: {canvas_background_color}")

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
        canvas_background_color = self.get_parameter_value("canvas_background_color") or "#ffffff"
        placeholder_url = f"data:image/svg+xml;base64,{self._create_placeholder_svg_base64(canvas_width, canvas_height, canvas_background_color)}"

        bash_image_artifact = ImageUrlArtifact(
            placeholder_url,
            meta={
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

        # Update bash image when canvas background color changes
        elif parameter.name == "canvas_background_color" and value is not None:
            logger.info(f"🎨 Updating background color to: {value}")
            # Update bash_image metadata with new background color
            bash_image_value = self.get_parameter_value("bash_image")
            if bash_image_value is not None:
                # Get current canvas dimensions
                canvas_width, canvas_height = self._get_canvas_dimensions()

                # Create new placeholder with updated background color
                new_placeholder_url = f"data:image/svg+xml;base64,{self._create_placeholder_svg_base64(canvas_width, canvas_height, value)}"
                logger.info(f"🎨 Created new placeholder URL with background color: {value}")

                if isinstance(bash_image_value, dict):
                    if "meta" not in bash_image_value:
                        bash_image_value["meta"] = {}
                    bash_image_value["value"] = new_placeholder_url
                    bash_image_value["meta"]["canvas_background_color"] = value
                    self.set_parameter_value("bash_image", bash_image_value)
                    logger.info("✅ Updated bash_image dict with new background color")
                else:
                    meta = getattr(bash_image_value, "meta", {})
                    if not isinstance(meta, dict):
                        meta = {}
                    bash_image_value.value = new_placeholder_url
                    meta["canvas_background_color"] = value
                    bash_image_value.meta = meta
                    self.set_parameter_value("bash_image", bash_image_value)
                    logger.info("✅ Updated bash_image artifact with new background color")

        if parameter.name == "input_images" and value is not None and len(value) > 0:
            # When input_images changes, update bash_image while preserving existing positions
            self._handle_input_image_change(value)

        if parameter.name == "bash_image" and value is not None:
            # Check if canvas_background_color has changed in the metadata
            if isinstance(value, dict):
                meta = value.get("meta", {})
            else:
                meta = getattr(value, "meta", {})

            metadata_background_color = meta.get("canvas_background_color")
            current_parameter_color = self.get_parameter_value("canvas_background_color")

            if metadata_background_color and metadata_background_color != current_parameter_color:
                logger.info(f"🎨 Syncing canvas_background_color from metadata: {metadata_background_color}")
                self.set_parameter_value("canvas_background_color", metadata_background_color)

            # Check if canvas dimensions have changed in the metadata
            canvas_size_meta = meta.get("canvas_size", {})
            metadata_width = canvas_size_meta.get("width")
            metadata_height = canvas_size_meta.get("height")

            if metadata_width and metadata_height:
                # Get current canvas dimensions from parameters
                current_width, current_height = self._get_canvas_dimensions()

                if metadata_width != current_width or metadata_height != current_height:
                    logger.info(f"📏 Syncing canvas dimensions from metadata: {metadata_width}x{metadata_height}")

                    # Set canvas_size to custom
                    self.set_parameter_value("canvas_size", "custom")

                    # Update width and height parameters
                    self.set_parameter_value("width", metadata_width)
                    self.set_parameter_value("height", metadata_height)

        # Initialize bash_image with current parameters if it's still using default values
        if parameter.name in ["canvas_size", "canvas_background_color"] and value is not None:
            bash_image_value = self.get_parameter_value("bash_image")
            if bash_image_value is not None:
                # Check if this is the first time setting these parameters
                if (
                    isinstance(bash_image_value, dict)
                    and bash_image_value.get("meta", {}).get("canvas_background_color") == "#ffffff"
                ):
                    # Update the bash_image to reflect current parameters
                    canvas_width, canvas_height = self._get_canvas_dimensions()
                    canvas_background_color = self.get_parameter_value("canvas_background_color") or "#ffffff"

                    # Create new placeholder with current parameters
                    new_placeholder_url = f"data:image/svg+xml;base64,{self._create_placeholder_svg_base64(canvas_width, canvas_height, canvas_background_color)}"

                    bash_image_value["value"] = new_placeholder_url
                    bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
                    bash_image_value["meta"]["canvas_background_color"] = canvas_background_color
                    bash_image_value["meta"]["viewport"] = {
                        "x": 0,
                        "y": 0,
                        "scale": 1.0,
                        "center_x": canvas_width // 2,
                        "center_y": canvas_height // 2,
                    }
                    self.set_parameter_value("bash_image", bash_image_value)

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get bash_image and create composited output
        bash_image = self.get_parameter_value("bash_image")
        composited_output = self._composite_layers_to_image(bash_image)

        if composited_output is not None:
            self.parameter_output_values["output_image"] = composited_output

    def _update_composited_output(self) -> None:
        """Update the output_image with the composited result."""
        logger.info("🔄 Updating composited output...")
        bash_image = self.get_parameter_value("bash_image")
        logger.info(f"🎨 Bash image: {bash_image is not None}")

        composited_output = self._composite_layers_to_image(bash_image)
        logger.info(f"🎨 Composited output: {composited_output is not None}")

        if composited_output is not None:
            self.parameter_output_values["output_image"] = composited_output
            logger.info("✅ Output image updated successfully")
        else:
            logger.info("❌ No composited output generated")
