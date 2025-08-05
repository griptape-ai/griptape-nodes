import uuid
from typing import Any

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import (
    cleanup_temp_files,
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

        # Grid dimensions
        self.columns = Parameter(
            name="columns",
            type="int",
            default_value=4,
            tooltip="Number of columns in the grid",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"slider": {"min_val": 1, "max_val": 10, "step": 1}},
        )
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
            default_value=True,
            tooltip="Use transparent background instead of solid color",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.transparent_bg)

        self.background_color = Parameter(
            name="background_color",
            type="str",
            default_value="#000000",
            tooltip="Background color of the grid (hex color)",
            ui_options={"hidden": True},
        )
        self.add_parameter(self.background_color)
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
        if parameter.name == "transparent_bg":
            if value:
                self.hide_parameter_by_name("background_color")
            else:
                self.show_parameter_by_name("background_color")
        if parameter.name == "output_format" and value == "jpeg":
            self.set_parameter_value("transparent_bg", False)
            self.publish_update_to_parameter("transparent_bg", False)
            self.show_parameter_by_name("background_color")
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        try:
            # Get parameters
            images = self.get_parameter_value("images")
            layout_style = self.get_parameter_value("layout_style")
            columns = self.get_parameter_value("columns")
            output_image_width = self.get_parameter_value("output_image_width")
            spacing = self.get_parameter_value("spacing")
            background_color = self.get_parameter_value("background_color")
            border_radius = self.get_parameter_value("border_radius")
            crop_to_fit = self.get_parameter_value("crop_to_fit")
            output_format = self.get_parameter_value("output_format")
            transparent_bg = self.get_parameter_value("transparent_bg")

            # Validate inputs
            if not images:
                # Create a placeholder image
                placeholder_image = create_placeholder_image(400, 300, background_color, transparent_bg=transparent_bg)
                # Save and create URL for placeholder
                filename = f"{uuid.uuid4()}.{output_format}"
                static_url = GriptapeNodes.StaticFilesManager().save_static_file(
                    image_to_bytes(placeholder_image, output_format),
                    filename,
                )
                url_artifact = ImageUrlArtifact(value=static_url)
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
                    crop_to_fit=crop_to_fit,
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
                )

            # Save the grid image and create URL
            filename = f"{uuid.uuid4()}.{output_format}"
            static_url = GriptapeNodes.StaticFilesManager().save_static_file(
                image_to_bytes(grid_image, output_format), filename
            )
            url_artifact = ImageUrlArtifact(value=static_url)
            self.publish_update_to_parameter("output", url_artifact)

        finally:
            # Always clean up temporary files
            cleanup_temp_files()
