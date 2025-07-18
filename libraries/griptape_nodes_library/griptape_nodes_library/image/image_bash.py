from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
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

        self.add_parameter(
            Parameter(
                name="bash_image",
                default_value=None,
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

        if isinstance(bash_image_value, dict):
            if "meta" not in bash_image_value:
                bash_image_value["meta"] = {}

            # Update konva_json with new canvas dimensions
            konva_json = bash_image_value["meta"].get("konva_json", {"images": [], "lines": []})

            bash_image_value["meta"]["konva_json"] = konva_json
            bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
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
                            "x": x,
                            "y": y,
                            "width": width,
                            "height": height,
                            "rotation": 0,
                            "scaleX": 1.0,
                            "scaleY": 1.0,
                        }
                    )

            # If bash_image is a dict, update its metadata
            if isinstance(bash_image_value, dict):
                if "meta" not in bash_image_value:
                    bash_image_value["meta"] = {}

                # Update konva_json while preserving lines
                existing_konva["images"] = konva_images

                bash_image_value["meta"]["input_images"] = input_images
                bash_image_value["meta"]["konva_json"] = existing_konva
                bash_image_value["meta"]["canvas_size"] = {"width": canvas_width, "height": canvas_height}
                self.set_parameter_value("bash_image", bash_image_value)
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

        # Create a new bash_image artifact with the new format
        # Use a placeholder URL for the bash_image value - the actual canvas is defined in konva_json
        canvas_width, canvas_height = self._get_canvas_dimensions()

        # Use a simple placeholder URL - the actual canvas is defined by canvas_size and konva_json
        placeholder_url = "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMSIgaGVpZ2h0PSIxIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxIiBoZWlnaHQ9IjEiIGZpbGw9InRyYW5zcGFyZW50Ii8+PC9zdmc+"

        bash_image_artifact = ImageUrlArtifact(
            placeholder_url,
            meta={
                "input_images": input_images,
                "konva_json": konva_json,
                "canvas_size": {"width": canvas_width, "height": canvas_height},
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

        if parameter.name == "input_images" and value is not None and len(value) > 0:
            # When input_images changes, update bash_image while preserving existing positions
            self._handle_input_image_change(value)

        if parameter.name == "bash_image" and value is not None:
            # Create clean output image without konva_json metadata
            clean_output = self._create_clean_output_image(value)
            if clean_output is not None:
                self.parameter_output_values["output_image"] = clean_output

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get bash_image and create clean output without konva_json metadata
        bash_image = self.get_parameter_value("bash_image")
        clean_output = self._create_clean_output_image(bash_image)

        if clean_output is not None:
            self.parameter_output_values["output_image"] = clean_output
