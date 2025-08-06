import os
from typing import Any

from griptape.loaders import PdfLoader, TextLoader

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.file_system_picker import FileSystemPicker


class LoadText(ControlNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Define supported file formats
        self.supported_formats = (
            ".data",
            ".env",
            ".info",
            ".json",
            ".log",
            ".text",
            ".txt",
            ".yaml",
            ".yml",
            ".csv",
            ".tsv",
            ".md",
            ".pdf",
        )

        # Add output parameters
        self.path = Parameter(
            name="path",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str"],
            type="str",
            default_value="",
            tooltip="The full path to the loaded file.",
        )
        self.path.add_trait(
            FileSystemPicker(
                allow_files=True,
                allow_directories=False,
                multiple=False,
                file_types=[
                    ".txt",
                    ".md",
                    ".pdf",
                    ".json",
                    ".yaml",
                    ".yml",
                    ".csv",
                    ".tsv",
                    ".py",
                    ".data",
                    ".env",
                    ".info",
                    ".log",
                ],
            )
        )

        self.add_parameter(self.path)

        self.add_parameter(
            Parameter(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                default_value="",
                tooltip="The text content of the loaded file.",
                ui_options={"multiline": True, "placeholder_text": "Text will load here."},
            )
        )

    def process(self) -> None:
        # Get the selected file
        text_path = self.parameter_values["path"]

        # Load file content based on extension
        ext = os.path.splitext(text_path)[1]  # noqa: PTH122
        if ext.lower() == ".pdf":
            text_data = PdfLoader().load(text_path)[0]
        else:
            text_data = TextLoader().load(text_path)

        # Set output values
        self.parameter_output_values["path"] = text_path
        self.parameter_output_values["output"] = text_data.value

        # Also set in parameter_values for get_value compatibility
        self.parameter_values["path"] = text_path
        self.parameter_values["output"] = text_data.value
