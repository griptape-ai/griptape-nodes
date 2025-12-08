from typing import Any

from griptape.artifacts import ImageUrlArtifact
from PIL import UnidentifiedImageError

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.clamp import Clamp
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    DEFAULT_PLACEHOLDER_HEIGHT,
    DEFAULT_PLACEHOLDER_WIDTH,
    cleanup_temp_files,
    create_background_image,
    create_grid_layout,
    create_masonry_layout,
    create_placeholder_image,
    image_to_bytes,
)


class DisplayImageGrid(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Input parameter for the list of image paths
        self.images = Parameter(
            name="images",
            type="list",
            default_value=None,
            tooltip="List of image file paths or ImageUrlArtifact objects to display in the grid",
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.images)

        # Layout style parameter
        self.layout_style = Parameter(
            name="layout_style",
            type="str",
            default_value="grid",
            tooltip="Layout style: 'grid' for uniform tiles, 'masonry' for variable heights",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )

        self.layout_style.add_trait(Options(choices=["grid", "masonry"]))
        self.add_parameter(self.layout_style)

        # Grid justification parameter
        self.grid_justification = Parameter(
            name="grid_justification",
            type="str",
            default_value="left",
            tooltip="How to justify images in grid layout (grid layout only)",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.grid_justification.add_trait(Options(choices=["left", "center", "right"]))
        self.add_parameter(self.grid_justification)

        # Grid dimensions
        self.columns = Parameter(
            name="columns",
            type="int",
            default_value=4,
            tooltip="Number of columns in the grid",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"slider": {"min_val": 1, "max_val": 10, "step": 1}},
        )
        self.columns.add_trait(Clamp(min_val=1, max_val=10))
        self.add_parameter(self.columns)

        # Spacing and styling
        self.add_parameter(
            Parameter(
                name="spacing",
                type="int",
                default_value=10,
                tooltip="Spacing between images in pixels",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"slider": {"min_val": 0, "max_val": 100, "step": 1}},
            )
        )

        self.border_radius = Parameter(
            name="border_radius",
            type="int",
            default_value=8,
            tooltip="Border radius for rounded corners (0 for square)",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"slider": {"min_val": 0, "max_val": 500, "step": 1}},
        )
        self.add_parameter(self.border_radius)

        # Crop to fit parameter
        self.crop_to_fit = Parameter(
            name="crop_to_fit",
            type="bool",
            default_value=True,
            tooltip="Crop images to fit perfectly within the grid/masonry for clean borders",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.crop_to_fit)

        # Transparent background parameter
        self.transparent_bg = Parameter(
            name="transparent_bg",
            type="bool",
            default_value=False,
            tooltip="Use transparent background instead of solid color",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.transparent_bg)

        self.background_color = Parameter(
            name="background_color",
            type="str",
            default_value="#000000",
            tooltip="Background color of the grid (hex color)",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            traits={ColorPicker(format="hex")},
        )
        self.add_parameter(self.background_color)

        # Output image size mode parameter
        self.output_image_size = Parameter(
            name="output_image_size",
            type="str",
            default_value="custom",
            tooltip="Use custom width or preset sizes",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.output_image_size.add_trait(Options(choices=["custom", "preset"]))
        self.add_parameter(self.output_image_size)

        # Output preset parameter (hidden by default)
        self.output_preset = Parameter(
            name="output_preset",
            type="str",
            default_value="1080p (1920x1080)",
            tooltip="Preset output size",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"hide": True},
        )
        self.output_preset.add_trait(
            Options(choices=["4K (3840x2160)", "1440p (2560x1440)", "1080p (1920x1080)", "720p (1280x720)"])
        )
        self.add_parameter(self.output_preset)

        self.output_image_width = Parameter(
            name="output_image_width",
            type="int",
            default_value=1200,
            tooltip="Maximum width of the output image in pixels",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.output_image_width)

        # Output format parameter
        self.output_format = Parameter(
            name="output_format",
            type="str",
            default_value="png",
            tooltip="Output format for the generated image grid",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.output_format.add_trait(Options(choices=["png", "jpeg", "webp"]))
        self.add_parameter(self.output_format)

        # Output parameter
        self.output = Parameter(
            name="output",
            type="ImageUrlArtifact",
            default_value=None,
            tooltip="Generated image grid",
            allowed_modes={ParameterMode.OUTPUT},
            ui_options={"pulse_on_run": True},
        )
        self.add_parameter(self.output)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "layout_style":
            if value == "masonry":
                self.hide_parameter_by_name("grid_justification")
            else:
                self.show_parameter_by_name("grid_justification")
        if parameter.name == "output_image_size":
            if value == "custom":
                self.show_parameter_by_name("output_image_width")
                self.hide_parameter_by_name("output_preset")
            else:  # preset
                self.hide_parameter_by_name("output_image_width")
                self.show_parameter_by_name("output_preset")
        if parameter.name == "transparent_bg":
            if value:
                self.hide_parameter_by_name("background_color")
            else:
                self.show_parameter_by_name("background_color")
        if parameter.name == "output_format" and value == "jpeg":
            self.set_parameter_value("transparent_bg", False)
            self.publish_update_to_parameter(
                "transparent_bg", False
            )  # TODO(griptape): Remove this when we know updates are working consistently: https://github.com/griptape-ai/griptape-nodes/issues/1843
            self.show_parameter_by_name("background_color")
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions: list[Exception] = []
        if not self.get_parameter_value("images"):
            msg = f"{self.name}: Images parameter is required"
            exceptions.append(ValueError(msg))
        if not self.get_parameter_value("output_image_width"):
            msg = f"{self.name}: Output image width parameter is required"
            exceptions.append(ValueError(msg))
        if self.get_parameter_value("output_image_width") <= 0:
            msg = f"{self.name}: Output image width must be greater than 0"
            exceptions.append(ValueError(msg))
        if self.get_parameter_value("columns") <= 0:
            msg = f"{self.name}: Columns parameter must be greater than 0"
            exceptions.append(ValueError(msg))
        return exceptions

    def _get_output_dimensions(
        self, output_image_size: str, output_preset: str, output_image_width_param: int
    ) -> tuple[int, int | None, bool]:
        """Determine output dimensions based on size mode.

        Returns:
            tuple: (output_image_width, output_image_height, use_preset_dimensions)
        """
        if output_image_size == "preset":
            preset_dimensions = {
                "4K": (3840, 2160),
                "1440p": (2560, 1440),
                "1080p": (1920, 1080),
                "720p": (1280, 720),
            }
            output_image_width, output_image_height = preset_dimensions.get(output_preset, (1920, 1080))
            return output_image_width, output_image_height, True
        # custom
        return output_image_width_param, None, False

    def _create_placeholder(
        self, background_color: str, *, transparent_bg: bool, output_format: str
    ) -> ImageUrlArtifact:
        """Create and save a placeholder image when no images are provided."""
        placeholder_image = create_placeholder_image(
            DEFAULT_PLACEHOLDER_WIDTH,
            DEFAULT_PLACEHOLDER_HEIGHT,
            background_color,
            transparent_bg=transparent_bg,
        )
        filename = generate_filename(
            node_name=self.name,
            suffix="_placeholder",
            extension=output_format,
        )
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(
            image_to_bytes(placeholder_image, output_format),
            filename,
        )
        return ImageUrlArtifact(value=static_url)

    def _scale_grid_to_fit(self, grid_image: Any, target_width: int, target_height: int) -> tuple[Any, int, int]:
        """Scale grid image to fit within target dimensions.

        Returns:
            tuple: (scaled_image, final_width, final_height)
        """
        from PIL import Image

        grid_width = grid_image.width
        grid_height = grid_image.height

        # Calculate scaling factor to fit within preset dimensions
        width_ratio = target_width / grid_width
        height_ratio = target_height / grid_height
        scale_factor = min(width_ratio, height_ratio, 1.0)  # Don't upscale, only downscale

        # Resize grid if needed
        if scale_factor < 1.0:
            new_width = int(grid_width * scale_factor)
            new_height = int(grid_height * scale_factor)
            return grid_image.resize((new_width, new_height), Image.Resampling.LANCZOS), new_width, new_height

        return grid_image, grid_width, grid_height

    def _apply_preset_canvas(
        self,
        grid_image: Any,
        target_dimensions: tuple[int, int],
        *,
        background_color: str,
        grid_justification: str,
        transparent_bg: bool,
    ) -> Any:
        """Apply preset dimensions by scaling grid and placing on exact-sized canvas.

        Args:
            grid_image: The grid image to scale and place on canvas
            target_dimensions: Tuple of (width, height) for the target canvas
            background_color: Background color for the canvas
            grid_justification: Horizontal alignment (left/center/right)
            transparent_bg: Whether to use transparent background
        """
        output_image_width, output_image_height = target_dimensions

        # Scale grid to fit within preset dimensions
        grid_image, grid_width, grid_height = self._scale_grid_to_fit(
            grid_image, output_image_width, output_image_height
        )

        # Create canvas with exact preset dimensions
        canvas = create_background_image(
            output_image_width, output_image_height, background_color, transparent_bg=transparent_bg
        )

        # Calculate position based on justification (horizontal) and center vertically
        y_offset = (output_image_height - grid_height) // 2

        # Apply justification for horizontal positioning
        if grid_justification == "center":
            x_offset = (output_image_width - grid_width) // 2
        elif grid_justification == "right":
            x_offset = output_image_width - grid_width
        else:  # left
            x_offset = 0

        # Paste grid onto canvas
        canvas.paste(grid_image, (x_offset, y_offset), grid_image if grid_image.mode == "RGBA" else None)
        return canvas

    def process(self) -> AsyncResult[None]:
        """Non-blocking entry point for Griptape engine."""
        yield lambda: self._process_sync()

    def _process_sync(self) -> None:
        """Synchronous processing of the image grid."""
        try:
            # Get parameters
            images = self.get_parameter_value("images")
            layout_style = self.get_parameter_value("layout_style")
            columns = self.get_parameter_value("columns")
            output_image_size = self.get_parameter_value("output_image_size")
            output_preset = self.get_parameter_value("output_preset")
            output_image_width_param = self.get_parameter_value("output_image_width")
            spacing = self.get_parameter_value("spacing")
            background_color = self.get_parameter_value("background_color")
            border_radius = self.get_parameter_value("border_radius")
            crop_to_fit = self.get_parameter_value("crop_to_fit")
            output_format = self.get_parameter_value("output_format")
            transparent_bg = self.get_parameter_value("transparent_bg")
            grid_justification = self.get_parameter_value("grid_justification")

            # Determine actual output dimensions
            output_image_width, output_image_height, use_preset_dimensions = self._get_output_dimensions(
                output_image_size, output_preset, output_image_width_param
            )

            # Handle empty images
            if not images:
                url_artifact = self._create_placeholder(
                    background_color, transparent_bg=transparent_bg, output_format=output_format
                )
                self.publish_update_to_parameter("output", url_artifact)
                return

            # Create grid based on layout style
            if layout_style.lower() == "masonry":
                grid_image = create_masonry_layout(
                    images,
                    columns,
                    output_image_width,
                    spacing,
                    background_color,
                    border_radius,
                    transparent_bg=transparent_bg,
                )
            else:  # grid layout
                grid_image = create_grid_layout(
                    images,
                    columns,
                    output_image_width,
                    spacing,
                    background_color,
                    border_radius,
                    crop_to_fit=crop_to_fit,
                    transparent_bg=transparent_bg,
                    justification=grid_justification,
                )

            # Apply preset canvas if needed
            if use_preset_dimensions and output_image_height is not None:
                grid_image = self._apply_preset_canvas(
                    grid_image,
                    (output_image_width, output_image_height),
                    background_color=background_color,
                    grid_justification=grid_justification,
                    transparent_bg=transparent_bg,
                )

            # Save the grid image and create URL
            filename = generate_filename(
                node_name=self.name,
                suffix="_grid",
                extension=output_format,
            )
            static_url = GriptapeNodes.StaticFilesManager().save_static_file(
                image_to_bytes(grid_image, output_format), filename
            )
            url_artifact = ImageUrlArtifact(value=static_url)
            self.publish_update_to_parameter("output", url_artifact)

        except (RuntimeError, OSError, UnidentifiedImageError) as e:
            msg = f"{self.name}: Error creating image grid: {e}"
            raise RuntimeError(msg) from e
        finally:
            # Always clean up temporary files
            cleanup_temp_files()
