from pathlib import Path

from griptape.loaders import ImageLoader

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.button import Button
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import dict_to_image_artifact

DEFAULT_FILENAME = "griptape_nodes.png"

MODES = ["connect", "load", "save"]


class Image(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Define the category and description
        self.category = "Image"
        self.description = "Unified image node for loading, saving, and manipulating images"

        # Image input/output parameter
        image_parameter = Parameter(
            name="image",
            input_types=["ImageArtifact", "dict"],
            type="ImageArtifact",
            output_type="ImageArtifact",
            # ui_options={"clickable_file_browser": True, "expander": True},
            tooltip="The image to process",
        )
        self.add_parameter(image_parameter)

        # Add operation mode parameter (load, save, display, etc.)
        mode_param = Parameter(
            name="operation",
            input_types=["str"],
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=MODES[0],
            traits={Options(choices=MODES)},
            tooltip="Operation to perform: 'load', 'save', 'display', etc.",
        )
        mode_param.add_trait(Options(choices=MODES))
        self.add_parameter(mode_param)

        # Add output path parameter for save operations
        self.add_parameter(
            Parameter(
                name="input_path",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=DEFAULT_FILENAME,
                tooltip="The input filename with extension (.png, .jpg, etc.) when saving",
                traits={Button(button_type="save")},
                ui_options={"clickable_file_browser": True, "expander": True},
            )
        )

        # Add output path parameter for save operations
        self.add_parameter(
            Parameter(
                name="output_path",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=DEFAULT_FILENAME,
                tooltip="The output filename with extension (.png, .jpg, etc.) when saving",
                traits={Button(button_type="save")},
                ui_options={"clickable_file_browser": True, "expander": True},
            )
        )

        # Clean the node up visually right away
        self._update_display(MODES[0])

    def after_value_set(self, parameter: Parameter, value=None, modified_parameters_set=None) -> None:  # noqa: ARG002
        if parameter.name == "operation":
            operation = self.parameter_values.get("operation", "load")
            self._update_display(operation)

    def _update_display(self, operation: str = MODES[0]) -> None:
        connect = self.get_parameter_by_name("image")
        input_path = self.get_parameter_by_name("input_path")
        output_path = self.get_parameter_by_name("output_path")

        if connect is not None:
            connect.ui_options = connect.ui_options or {}
            connect.ui_options = connect.ui_options | {"hide": operation != MODES[0]}

        if input_path is not None:
            input_path.ui_options = input_path.ui_options or {}
            input_path.ui_options = input_path.ui_options | {"hide": operation == MODES[0]}

        if output_path is not None:
            output_path.ui_options = output_path.ui_options or {}
            output_path.ui_options = output_path.ui_options | {"hide": operation != MODES[0] and operation != MODES[2]}

    def process(self) -> None:
        """Process the image based on the selected operation."""
        operation = self.parameter_values.get("operation", "load")

        # Dispatch to the appropriate operation method
        if operation == MODES[0]:  # load"
            self._load_operation()
        elif operation == MODES[1]:  # save
            self._save_operation()
        else:
            msg = f"Unknown operation: {operation}"
            raise ValueError(msg)

    def _load_operation(self) -> None:
        image = self.parameter_values["image"]
        image_artifact = dict_to_image_artifact(image)
        self.parameter_output_values["image"] = image_artifact

    def _save_operation(self) -> None:
        config_manager = GriptapeNodes.ConfigManager()
        workspace_path = Path(config_manager.workspace_path)

        image = self.parameter_values.get("image")

        if not image:
            logger.info("No image provided to save")
            return

        output_file = self.parameter_values.get("output_path", DEFAULT_FILENAME)

        # Set output values BEFORE transforming to workspace-relative
        self.parameter_output_values["output_path"] = output_file

        full_output_file = str(workspace_path / output_file)

        try:
            if isinstance(image, dict):
                image_artifact = dict_to_image_artifact(image)
            else:
                image_artifact = image

            # Use ImageLoader to save the image
            loader = ImageLoader()
            loader.save(full_output_file, image_artifact)

            success_msg = f"Saved image: {full_output_file}"
            logger.info(success_msg)

        except Exception as e:
            error_message = str(e)
            msg = f"Error saving image: {error_message}"
            raise ValueError(msg) from e
