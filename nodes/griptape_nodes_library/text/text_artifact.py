from pathlib import Path
from typing import Any

from griptape.artifacts import TextArtifact
from griptape.loaders import TextLoader

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.button import Button
from griptape_nodes.traits.options import Options

DEFAULT_FILENAME = "griptape_text.txt"

MODES = ["graph", "file"]
MODE_NAME = "source"


class Text(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        # Define the category and description
        self.category = "Text"
        self.description = "Unified text node for loading, saving, inputting, and manipulating text"

        # Text input/output parameter
        text_param = Parameter(
            name="text",
            default_value=value,
            input_types=["str"],
            output_type="str",
            type="str",
            tooltip="The text content to save to file",
            ui_options={"multiline": True},
        )
        self.add_parameter(text_param)

        # Add operation mode parameter (connect, load, save, input)
        mode_param = Parameter(
            name=MODE_NAME,
            input_types=["str"],
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=MODES[0],
            traits={Options(choices=MODES)},
            tooltip=f"{MODE_NAME} : {' or '.join(MODES)}",
        )
        mode_param.add_trait(Options(choices=MODES))
        self.add_parameter(mode_param)

        # Add input path parameter for load operations
        self.add_parameter(
            Parameter(
                name="input_path",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=DEFAULT_FILENAME,
                tooltip="The input filename with extension (.txt, .md, etc.) when loading",
                traits={Button(button_type="open")},
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
                tooltip="The output filename with extension (.txt, .md, etc.) when saving",
                traits={Button(button_type="save")},
                ui_options={"clickable_file_browser": True, "expander": True},
            )
        )

        # Clean the node up visually right away
        # self._update_display(MODES[0])

    def after_incoming_connection(self, source_node, source_parameter, target_parameter: Parameter) -> None:
        if target_parameter.name == "text":
            # Get the operation parameter
            operation_param = self.get_parameter_by_name(MODE_NAME)

            if operation_param is not None:
                # Set the operation value to 'graph' mode
                self.parameter_values[MODE_NAME] = MODES[0]  # MODES[0] is 'grapj' mode
                text_param = self.get_parameter_by_name("text")
                # text_param.allowed_modes = ({ParameterMode.PROPERTY, ParameterMode.OUTPUT},)
                text_param.settable = False

    """
    def after_value_set(self, parameter: Parameter, value=None, modified_parameters_set=None) -> None:
        if parameter.name == MODE_NAME:
            operation = self.parameter_values.get(MODE_NAME, MODES[0])
            self._update_display(operation)

    def _update_display(self, operation: str = MODES[0]) -> None:
        text_param = self.get_parameter_by_name("text")
        input_path = self.get_parameter_by_name("input_path")
        output_path = self.get_parameter_by_name("output_path")

        # Initialize ui_options if None
        for param in [text_param, input_path]:
            if param is not None:
                param.ui_options = param.ui_options or {}

        # Configure UI for all mode
        if operation == MODES[0]:  # graph
            text_param.ui_options = text_param.ui_options | {"hide": False}  # type: ignore  # noqa: PGH003
            input_path.ui_options = input_path.ui_options | {"hide": True}  # type: ignore  # noqa: PGH003
            output_path.ui_options = input_path.ui_options | {"hide": False}  # type: ignore  # noqa: PGH003

        # Configure UI for connect mode
        elif operation == MODES[1]:  # file
            text_param.ui_options = text_param.ui_options | {"hide": False}  # type: ignore  # noqa: PGH003
            input_path.ui_options = input_path.ui_options | {"hide": False}  # type: ignore  # noqa: PGH003
            output_path.ui_options = input_path.ui_options | {"hide": True}  # type: ignore  # noqa: PGH003
    """

    def _create_text_artifact(self, text_content):
        # Create a TextArtifact from string input.
        # If already a TextArtifact, return as is
        if hasattr(text_content, "__class__") and text_content.__class__.__name__ == "TextArtifact":
            return text_content

        # Convert string to TextArtifact
        if isinstance(text_content, str):
            return TextArtifact(
                value=text_content,
                encoding="utf-8",
            )

        # Default fallback
        return TextArtifact(
            value=str(text_content),
            encoding="utf-8",
        )

    def process(self) -> None:
        """Process the text based on the selected operation."""
        operation = self.parameter_values.get("operation", MODES[0])

        # Dispatch to the appropriate operation method
        if operation == MODES[0]:  # graph
            self._connect_operation()
        elif operation == MODES[1]:  # file
            self._load_operation()

    def _connect_operation(self) -> None:
        """Pass through text data from input to output."""
        text = self.parameter_values.get("text", "")
        text_artifact = self._create_text_artifact(text)
        self.parameter_output_values["text"] = text_artifact

    def _load_operation(self) -> None:
        """Load text from file."""
        input_file = self.parameter_values.get("input_path", DEFAULT_FILENAME)

        try:
            # Use TextLoader to load the text
            loader = TextLoader()
            text_artifact = loader.load(input_file)

            # Set output values
            self.parameter_output_values["text"] = text_artifact
            self.parameter_output_values["input_path"] = input_file

            logger.info(f"Loaded text from: {input_file}")

        except Exception as e:
            error_message = str(e)
            msg = f"Error loading text: {error_message}"
            raise ValueError(msg) from e

    def _save_operation(self) -> None:
        """Save text to file."""
        config_manager = GriptapeNodes.ConfigManager()
        workspace_path = Path(config_manager.workspace_path)

        text = self.parameter_values.get("text")

        if not text:
            logger.info("No text provided to save")
            return

        output_file = self.parameter_values.get("output_path", DEFAULT_FILENAME)

        # Set output values BEFORE transforming to workspace-relative
        self.parameter_output_values["output_path"] = output_file

        # Create full path
        full_output_file = str(workspace_path / output_file)

        try:
            # Convert to TextArtifact if needed
            text_artifact = self._create_text_artifact(text)

            # Use TextLoader to save the text
            loader = TextLoader()
            loader.save(full_output_file, text_artifact)

            success_msg = f"Saved text to: {full_output_file}"
            logger.info(success_msg)

        except Exception as e:
            error_message = str(e)
            msg = f"Error saving text: {error_message}"
            raise ValueError(msg) from e

    def _input_operation(self) -> None:
        """Use manually entered text."""
        input_text = self.parameter_values.get("input_text", "")

        # Create TextArtifact from the input
        text_artifact = self._create_text_artifact(input_text)

        # Set output values
        self.parameter_output_values["text"] = text_artifact
