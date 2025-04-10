from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.button import Button


class SaveText(ControlNode):
    """Save text to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add text input parameter
        self.add_parameter(
            Parameter(
                name="text",
                input_types=["str"],
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip="The text content to save to file",
                ui_options={"multiline": True, "placeholder_text": "Text to save to a file..."},
            )
        )

        # Add filename prefix parameter
        self.add_parameter(
            Parameter(
                name="output_path",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="griptape_output.txt",
                tooltip="The output filename",
                traits={Button(button_type="save")},
            )
        )

    def process(self) -> None:
        """Process the node by saving text to a file."""
        text = self.parameter_values.get("text", "")
        full_output_file = self.parameter_values.get("output_path", "griptape_output.txt")

        try:
            with Path(full_output_file).open("w") as f:
                f.write(text)
            success_msg = f"Saved file: {full_output_file}"
            logger.info(success_msg)

            # Set output values
            self.parameter_output_values["output_path"] = full_output_file

        except Exception as e:
            error_message = str(e)
            msg = f"Error saving file: {error_message}"
            raise ValueError(msg) from e

        """
        Should this ^^^ work more like this? :

        from griptape.artifacts import TextArtifact
        from griptape.loaders import TextLoader
        from rich import print
        myFile = "MyFile.txt"
        artifact = TextArtifact(
            value="This is some text",
            encoding="utf-8",
            meta={"jason": "is cool", "coffee": "is good"},
        )
        print(artifact)
        TextLoader().save(myFile, artifact)
        """
