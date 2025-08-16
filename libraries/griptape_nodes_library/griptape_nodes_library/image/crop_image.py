import io
import uuid
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from libraries.griptape_nodes_library.griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact


class CropImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "Image"
        self.description = "Crop an image to a specific size."

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                type="ImageUrlArtifact",
                default_value=None,
                tooltip="Input image to crop",
            )
        )

        # Crop coordinates
        self.add_parameter(
            Parameter(
                name="crop_left",
                type="int",
                default_value=0,
                tooltip="Left crop position in pixels (≥ 0)",
                traits={Slider(min_val=0, max_val=1000)},
            )
        )

        self.add_parameter(
            Parameter(
                name="crop_right",
                type="int",
                default_value=0,
                tooltip="Right crop position in pixels (≥ 0)",
                traits={Slider(min_val=0, max_val=1000)},
            )
        )

        self.add_parameter(
            Parameter(
                name="crop_top",
                type="int",
                default_value=0,
                tooltip="Top crop position in pixels (≥ 0)",
                traits={Slider(min_val=0, max_val=1000)},
            )
        )

        self.add_parameter(
            Parameter(
                name="crop_bottom",
                type="int",
                default_value=0,
                tooltip="Bottom crop position in pixels (≥ 0)",
                traits={Slider(min_val=0, max_val=1000)},
            )
        )

        # Transform parameters
        self.add_parameter(
            Parameter(
                name="zoom",
                type="float",
                default_value=1.0,
                tooltip="Zoom factor (1.0 = no zoom, 2.0 = 2x zoom in)",
                traits={Slider(min_val=1.0, max_val=10.0)},
            )
        )

        self.add_parameter(
            Parameter(
                name="rotation_deg",
                type="float",
                default_value=0.0,
                tooltip="Rotation in degrees (-180 to 180)",
                traits={Slider(min_val=-180.0, max_val=180.0)},
            )
        )

        # Pan parameters
        self.add_parameter(
            Parameter(
                name="pan_x",
                type="int",
                default_value=0,
                tooltip="Pan image horizontally (positive = right, negative = left)",
                traits={Slider(min_val=-1000, max_val=1000)},
            )
        )

        self.add_parameter(
            Parameter(
                name="pan_y",
                type="int",
                default_value=0,
                tooltip="Pan image vertically (positive = down, negative = up)",
                traits={Slider(min_val=-1000, max_val=1000)},
            )
        )

        self.add_parameter(
            Parameter(
                name="background_color",
                type="str",
                default_value="#00000000",
                tooltip="Background color (RGBA or hex) for transparent areas",
            )
        )

        self.add_parameter(
            Parameter(
                name="output_format",
                type="str",
                default_value="PNG",
                tooltip="Output format: PNG, JPEG, WEBP",
                traits={Options(choices=["PNG", "JPEG", "WEBP"])},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_quality",
                type="float",
                default_value=0.9,
                tooltip="Output quality (0.0 to 1.0) for lossy formats",
            )
        )

        # Output parameter
        self.add_parameter(
            Parameter(
                name="output",
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Cropped output image",
            )
        )

    def _crop(self) -> None:
        input_artifact = self.get_parameter_value("input_image")
        crop_left = self.get_parameter_value("crop_left")
        crop_right = self.get_parameter_value("crop_right")
        crop_top = self.get_parameter_value("crop_top")
        crop_bottom = self.get_parameter_value("crop_bottom")
        zoom = self.get_parameter_value("zoom")
        rotation_deg = self.get_parameter_value("rotation_deg")
        pan_x = self.get_parameter_value("pan_x")
        pan_y = self.get_parameter_value("pan_y")
        background_color = self.get_parameter_value("background_color")
        output_format = self.get_parameter_value("output_format")
        output_quality = self.get_parameter_value("output_quality")

        # Load image
        def load_img(artifact):
            if isinstance(artifact, dict):
                artifact = dict_to_image_url_artifact(artifact)
            if isinstance(artifact, ImageUrlArtifact):
                return Image.open(io.BytesIO(artifact.to_bytes()))
            if isinstance(artifact, ImageArtifact):
                return Image.open(io.BytesIO(artifact.value))
            raise ValueError("Invalid image artifact")

        img = load_img(input_artifact)
        original_width, original_height = img.size

        # Apply zoom in (crop a smaller area from the center)
        if zoom > 1.0:
            zoom_center_x = original_width / 2
            zoom_center_y = original_height / 2

            # Calculate new dimensions after zoom (smaller than original)
            new_width = int(original_width / zoom)
            new_height = int(original_height / zoom)

            # Calculate crop coordinates to zoom into center
            crop_x = int(zoom_center_x - new_width / 2)
            crop_y = int(zoom_center_y - new_height / 2)

            # Apply pan offset to zoom center
            crop_x += pan_x
            crop_y += pan_y

            # Ensure crop coordinates are within bounds
            crop_x = max(0, min(crop_x, original_width - new_width))
            crop_y = max(0, min(crop_y, original_height - new_height))

            print(
                f"Zoom in {zoom} + Pan ({pan_x}, {pan_y}): cropping to {new_width}x{new_height} at ({crop_x}, {crop_y})"
            )
            img = img.crop((crop_x, crop_y, crop_x + new_width, crop_y + new_height))

        # Apply rotation
        if rotation_deg != 0.0:
            # Convert background color to RGBA
            bg_color = self._parse_color(background_color)
            img = img.rotate(rotation_deg, expand=True, fillcolor=bg_color)

        # Apply manual crop coordinates
        img_width, img_height = img.size

        # Apply manual crop if coordinates are specified
        # Handle partial crop coordinates (e.g., only left or only top)
        if crop_left > 0 or crop_right > 0 or crop_top > 0 or crop_bottom > 0:
            # Set defaults for unspecified coordinates
            if crop_left == 0:
                crop_left = 0  # Start from left edge
            if crop_top == 0:
                crop_top = 0  # Start from top edge
            if crop_right == 0:
                crop_right = img_width  # End at right edge
            if crop_bottom == 0:
                crop_bottom = img_height  # End at bottom edge

            # Ensure crop coordinates are within image bounds
            crop_left = max(0, min(crop_left, img_width))
            crop_right = max(crop_left, min(crop_right, img_width))
            crop_top = max(0, min(crop_top, img_height))
            crop_bottom = max(crop_top, min(crop_bottom, img_height))

            # Additional safety check - ensure we have a valid crop area
            if crop_right > crop_left and crop_bottom > crop_top:
                try:
                    print(f"Cropping: left={crop_left}, top={crop_top}, right={crop_right}, bottom={crop_bottom}")
                    img = img.crop((crop_left, crop_top, crop_right, crop_bottom))
                except Exception as e:
                    print(f"Crop failed: {e}. Using original image.")
                    # If crop fails, continue with original image
            else:
                print("Invalid crop coordinates, skipping crop")

        # Save result
        img_byte_arr = io.BytesIO()

        # Determine save format and options
        save_format = output_format.upper()
        save_options = {}

        if save_format == "JPEG":
            save_options["quality"] = int(output_quality * 100)
            save_options["optimize"] = True
        elif save_format == "WEBP":
            save_options["quality"] = int(output_quality * 100)
            save_options["lossless"] = False

        img.save(img_byte_arr, format=save_format, **save_options)
        img_byte_arr = img_byte_arr.getvalue()

        static_url = GriptapeNodes.StaticFilesManager().save_static_file(
            img_byte_arr, f"cropped_{uuid.uuid4()}.{save_format.lower()}"
        )
        self.parameter_output_values["output"] = ImageUrlArtifact(value=static_url)

    def process(self) -> None:
        self._crop()

    def _parse_color(self, color_str: str) -> tuple[int, int, int, int]:
        """Parse color string to RGBA tuple"""
        if color_str.startswith("#"):
            # Hex color
            color_str = color_str[1:]
            if len(color_str) == 6:
                r = int(color_str[0:2], 16)
                g = int(color_str[2:4], 16)
                b = int(color_str[4:6], 16)
                return (r, g, b, 255)
            if len(color_str) == 8:
                r = int(color_str[0:2], 16)
                g = int(color_str[2:4], 16)
                b = int(color_str[4:6], 16)
                a = int(color_str[6:8], 16)
                return (r, g, b, a)
        return (0, 0, 0, 0)  # Default transparent

    def _resize_output(self, img: Image.Image, output_width: int | None, output_height: int | None) -> Image.Image:
        """Resize image to output dimensions"""
        if output_width is None and output_height is None:
            return img

        width, height = img.size

        if output_width is not None and output_height is not None:
            # Both dimensions specified
            return img.resize((output_width, output_height), Image.Resampling.LANCZOS)
        if output_width is not None:
            # Only width specified, maintain aspect ratio
            new_height = int(height * output_width / width)
            return img.resize((output_width, new_height), Image.Resampling.LANCZOS)
        if output_height is not None:
            # Only height specified, maintain aspect ratio
            new_width = int(width * output_height / height)
            return img.resize((new_width, output_height), Image.Resampling.LANCZOS)
        return img

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in {
            "crop_left",
            "crop_right",
            "crop_top",
            "crop_bottom",
            "zoom",
            "rotation_deg",
            "pan_x",
            "pan_y",
            "background_color",
            "output_format",
            "output_quality",
        }:
            self._crop()
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = []

        if not self.get_parameter_value("input_image"):
            msg = f"{self.name} - Input image is required"
            exceptions.append(Exception(msg))

        return exceptions

    def reset_node_state(self) -> None:
        """Reset the node to a clean state"""
        # Reset all crop parameters to defaults
        self.set_parameter_value("crop_left", 0)
        self.set_parameter_value("crop_right", 0)
        self.set_parameter_value("crop_top", 0)
        self.set_parameter_value("crop_bottom", 0)
        self.set_parameter_value("zoom", 1.0)
        self.set_parameter_value("rotation_deg", 0.0)
        self.set_parameter_value("background_color", "#00000000")
        self.set_parameter_value("output_format", "PNG")
        self.set_parameter_value("output_quality", 0.9)

        # Clear any cached data
        if hasattr(self, "_cached_image"):
            delattr(self, "_cached_image")

        # Clear output
        self.parameter_output_values["output"] = None
        print("Node state reset to defaults")

    def _update_crop_metadata(self) -> None:
        """Update the input image metadata with current crop parameters for GUI sync"""
        input_artifact = self.parameter_values.get("input_image")
        if input_artifact is None:
            return

        # Load image to get dimensions for default crop area
        try:

            def load_img(artifact):
                if isinstance(artifact, dict):
                    artifact = dict_to_image_url_artifact(artifact)
                if isinstance(artifact, ImageUrlArtifact):
                    return Image.open(io.BytesIO(artifact.to_bytes()))
                if isinstance(artifact, ImageArtifact):
                    return Image.open(io.BytesIO(artifact.value))
                raise ValueError("Invalid image artifact")

            img = load_img(input_artifact)
            img_width, img_height = img.size
        except:
            img_width, img_height = 100, 100  # Default fallback

        # Get current crop values, use full image if not set
        crop_left = self.parameter_values.get("crop_left", 0)
        crop_right = self.parameter_values.get("crop_right", 0)
        crop_top = self.parameter_values.get("crop_top", 0)
        crop_bottom = self.parameter_values.get("crop_bottom", 0)

        # If no crop is set, use full image
        if crop_left == 0 and crop_right == 0 and crop_top == 0 and crop_bottom == 0:
            crop_left = 0
            crop_right = img_width
            crop_top = 0
            crop_bottom = img_height

        # Create crop metadata for react-advanced-cropper
        crop_metadata = {
            "crop_coordinates": {
                "x": crop_left,
                "y": crop_top,
                "width": crop_right - crop_left,
                "height": crop_bottom - crop_top,
            },
            "transforms": {
                "scale": self.parameter_values.get("zoom", 1.0),
                "rotate": self.parameter_values.get("rotation_deg", 0.0),
            },
            "constraints": {
                "minWidth": 1,
                "minHeight": 1,
                "maxWidth": 4000,
                "maxHeight": 4000,
            },
            "output": {
                "width": self.parameter_values.get("output_width"),
                "height": self.parameter_values.get("output_height"),
                "format": self.parameter_values.get("output_format", "PNG"),
                "quality": self.parameter_values.get("output_quality", 0.9),
                "background": self.parameter_values.get("background_color", "#00000000"),
            },
        }

        # Update the input artifact metadata
        if hasattr(input_artifact, "metadata"):
            input_artifact.metadata = input_artifact.metadata or {}
            input_artifact.metadata["crop_settings"] = crop_metadata
