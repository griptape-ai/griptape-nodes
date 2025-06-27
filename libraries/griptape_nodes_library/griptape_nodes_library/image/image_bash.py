from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact

BASE_OPTIONS = ["HD", "2K", "4K", "A4", "A3", "square", "landscape", "portrait", "custom"]


class ImageBash(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # self.add_parameter(
        #     Parameter(
        #         name="base_canvas",
        #         default_value=BASE_OPTIONS[0],
        #         input_types=["string", "ImageArtifact", "ImageUrlArtifact"],
        #         type="string",
        #         tooltip="The size of the image to create, or connect a base image to use as a canvas",
        #         allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        #     )
        # )

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

    def _handle_input_image_change(self, value: Any) -> None:
        # Normalize input image to ImageUrlArtifact if needed
        image_artifact = value
        if isinstance(value, dict):
            image_artifact = dict_to_image_url_artifact(value)

        # Check and see if the bash_image is set
        bash_image_value = self.get_parameter_value("bash_image")
        if bash_image_value is None:
            self._create_new_bash_image(image_artifact)
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

            # Get canvas dimensions from the bash_image
            if isinstance(bash_image_value, dict):
                canvas_width, canvas_height = self._get_image_dimensions(bash_image_value["value"])
            else:
                canvas_width, canvas_height = self._get_image_dimensions(bash_image_value.value)

            for i, input_img in enumerate(input_images):
                # Try to find existing konva image data
                existing_konva_img = None
                if i < len(existing_konva.get("images", [])):
                    existing_konva_img = existing_konva["images"][i]

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
                bash_image_value.meta = meta
                self.set_parameter_value("bash_image", bash_image_value)

    def _create_new_bash_image(self, image_artifact: ImageUrlArtifact) -> None:
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

        # Get canvas dimensions from the first image
        canvas_width, canvas_height = self._get_image_dimensions(image_artifact.value)

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
        bash_image_artifact = ImageUrlArtifact(
            image_artifact.value, meta={"input_images": input_images, "konva_json": konva_json}
        )
        self.set_parameter_value("bash_image", bash_image_artifact)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "base_canvas" and value is not None:
            if isinstance(value, dict):
                value = dict_to_image_url_artifact(value)
            if isinstance(value, ImageUrlArtifact):
                self._create_new_bash_image(value)

        if parameter.name == "input_images" and value is not None and len(value) > 0:
            # When input_images changes, create/update bash_image with first image as base
            self._create_new_bash_image(value[0])

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
