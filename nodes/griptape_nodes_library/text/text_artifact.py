import os
from pathlib import Path
from typing import Any

from griptape.artifacts import TextArtifact
from griptape.loaders import PdfLoader, TextLoader

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: F401, N813
from griptape_nodes.traits.button import Button
from griptape_nodes.traits.options import Options

DEFAULT_INPUT_FILENAME = "griptape_text_input.txt"
DEFAULT_OUTPUT_FILENAME = "griptape_text_output.txt"

DEFAULT_MESSAGE = "Input or connect text here"
DEFAULT_FILE_MESSAGE = "Field will populate from a file"

MODES = ["workflow", "file"]
MODE_NAME = "source"


class Text(ControlNode):
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

        # Add operation mode parameter (connect, load, save, input)
        mode_param = Parameter(
            name=MODE_NAME,
            input_types=["str"],
            type="str",
            allowed_modes={ParameterMode.PROPERTY},
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
                default_value=DEFAULT_INPUT_FILENAME,
                tooltip="The input filename with extension (.txt, .md, etc.) when loading",
                traits={Button(button_type="open")},
                ui_options={"clickable_file_browser": True, "expander": True, "hide": True},
            )
        )

        # Text input/output parameter
        text_param = Parameter(
            name="text",
            default_value="",
            input_types=["str"],
            output_type="str",
            type="str",
            tooltip="The text content to save to file",
            ui_options={"multiline": True, "placeholder_text": DEFAULT_MESSAGE},
        )
        self.add_parameter(text_param)

        self.add_parameter(
            Parameter(
                name="save",
                input_types=["bool"],
                type="bool",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=False,
                tooltip="Expose the output_path and save the text",
                # traits={Button(button_type="save")},
                # ui_options={"clickable_file_browser": True, "expander": True},
            )
        )

        # Add output path parameter for save operations
        self.add_parameter(
            Parameter(
                name="output_path",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=DEFAULT_OUTPUT_FILENAME,
                tooltip="The output filename with extension (.txt, .md, etc.) when saving",
                traits={Button(button_type="save")},
                ui_options={"clickable_file_browser": True, "expander": True, "hide": True},
            )
        )

        # Clean the node up visually right away
        # self._update_display()

    """
    def after_incoming_connection(self, source_node, source_parameter, target_parameter: Parameter) -> None:  # noqa: ARG002
        if target_parameter.name == "text":
            self.parameter_values[MODE_NAME] = MODES[0]
            self.parameter_output_values[MODE_NAME] = MODES[0]
            self.after_value_set(parameter=target_parameter)"""

    def after_value_set(self, parameter: Parameter, value=None, modified_parameters_set=None) -> None:  # noqa: ARG002
        if parameter.name == MODE_NAME:
            # If we just changed to "file" mode, disconnect anything connected into "text"
            if value == MODES[1]:  # file mode
                con = cmd.get_connections_for_node(self.name)
                if hasattr(con, "incoming_connections"):
                    for c in con.incoming_connections:
                        if c.target_parameter_name == "text":
                            # Delete the connection
                            cmd.delete_connection(
                                source_node_name=c.source_node_name,
                                source_param_name=c.source_parameter_name,
                                target_node_name=self.name,
                                target_param_name="text",
                            )

            # Update the display after mode change
            self._update_display()

        if parameter.name == "save":
            self._update_display()

    def _update_display(self) -> None:
        operation = self.parameter_values.get(MODE_NAME, MODES[0])

        text_param = self.get_parameter_by_name("text")
        input_path = self.get_parameter_by_name("input_path")
        output_path = self.get_parameter_by_name("output_path")

        # Initialize ui_options if None
        for param in [text_param, input_path, output_path]:
            if param is not None:
                param.ui_options = param.ui_options or {}

        # Configure UI for graph mode
        if operation == MODES[0]:  # graph
            text_param.ui_options = text_param.ui_options | {"hide": False}  # type: ignore  # noqa: PGH003
            text_param.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT}
            text_param.ui_options = text_param.ui_options | {"placeholder_text": DEFAULT_MESSAGE}
            input_path.ui_options = input_path.ui_options | {"hide": True}  # type: ignore  # noqa: PGH003

        # Configure UI for file mode
        elif operation == MODES[1]:  # file
            text_param.allowed_modes = {ParameterMode.OUTPUT}
            text_param.ui_options = text_param.ui_options | {"placeholder_text": DEFAULT_FILE_MESSAGE}
            input_path.ui_options = input_path.ui_options | {"hide": False}  # type: ignore  # noqa: PGH003

        # Configure UI for save mode
        do_save = self.parameter_values.get("save", False)
        if do_save:  # save
            output_path.ui_options = output_path.ui_options | {"hide": False}  # type: ignore  # noqa: PGH003
        else:
            output_path.ui_options = output_path.ui_options | {"hide": True}  # type: ignore  # noqa: PGH003

    def _create_text_artifact(self, text_content) -> TextArtifact:
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
        operation = self.parameter_values.get(MODE_NAME, MODES[0])
        save = self.parameter_values.get("save", False)

        # Dispatch to the appropriate operation method
        if operation == MODES[0]:  # graph
            logger.info("Reading from workflow")
            self._connect_operation()
        elif operation == MODES[1]:  # file
            logger.info("Loading from file")
            self._load_operation()

        if save:
            self._save_operation()

    def _connect_operation(self) -> None:
        logger.info("INSIDE _connect_operation")

        """Pass through text data from input to output."""
        # text = self.parameter_values.get("text", "")
        # text_artifact = self._create_text_artifact(text)
        # self.parameter_output_values["text"] = text_artifact
        pass

    def _workspace_it(self, stub: str = "dummy.txt") -> str:
        config_manager = GriptapeNodes.ConfigManager()
        workspace_path = Path(config_manager.workspace_path)
        return str(workspace_path / stub)

    def _load_operation(self) -> None:
        logger.info("INSIDE _load_operation")
        """Load text from file."""
        input_file = self.parameter_values.get("input_path", DEFAULT_INPUT_FILENAME)
        input_file = self._workspace_it(input_file)
        logger.info(f'Loading text from "{input_file}"')

        # Load file content based on extension
        ext = os.path.splitext(input_file)[1]  # noqa: PTH122
        if ext.lower() == ".pdf":
            text_data = PdfLoader().load(input_file)[0]
        else:
            text_data = TextLoader().load(input_file)

        # Set output values
        self.parameter_values["text"] = text_data.value
        self.parameter_output_values["text"] = text_data.value

    def _save_operation(self) -> None:
        logger.info("INSIDE _save_operation")
        """Save text to file."""

        text = self.parameter_values.get("text")

        if not text:
            logger.info("No text provided to save")
            return

        output_file = self.parameter_values.get("output_path", DEFAULT_OUTPUT_FILENAME)

        # Set output values BEFORE transforming to workspace-relative
        self.parameter_output_values["output_path"] = output_file

        # Create full path
        output_file = self._workspace_it(output_file)

        try:
            # Convert to TextArtifact if needed
            text_artifact = self._create_text_artifact(text)

            # Use TextLoader to save the text
            loader = TextLoader()
            loader.save(output_file, text_artifact)

            success_msg = f"Saved text to: {output_file}"
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
