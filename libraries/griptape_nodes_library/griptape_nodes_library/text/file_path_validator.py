import os
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode


class FilePathValidator(ControlNode):
    """Validates that file paths exist and are readable Python files."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Input parameter for list of file paths
        self.add_parameter(
            Parameter(
                name="file_paths",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["list"],
                type="list",
                default_value=[],
                tooltip="List of file paths to validate",
                ui_options={"multiline": True, "placeholder_text": "Enter file paths to validate..."},
            )
        )

        # Output parameter for valid file paths
        self.add_parameter(
            Parameter(
                name="valid_paths",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="list",
                default_value=[],
                tooltip="List of valid file paths that exist and are readable",
            )
        )

        # Output parameter for validation errors
        self.add_parameter(
            Parameter(
                name="validation_errors",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                default_value="",
                tooltip="Validation errors for invalid file paths",
                ui_options={"multiline": True, "placeholder_text": "Validation errors will appear here..."},
            )
        )

    def process(self) -> None:
        """Process the node by validating file paths."""
        file_paths = self.parameter_values.get("file_paths", [])

        # Ensure file_paths is a list
        if not isinstance(file_paths, list):
            file_paths = [file_paths] if file_paths else []

        valid_paths = []
        errors = []

        for file_path in file_paths:
            try:
                # Convert to Path object for easier handling
                path = Path(file_path)

                # Check if file exists
                if not path.exists():
                    errors.append(f"File does not exist: {file_path}")
                    continue

                # Check if it's a file (not a directory)
                if not path.is_file():
                    errors.append(f"Path is not a file: {file_path}")
                    continue

                # Check if it's a Python file
                if path.suffix.lower() != ".py":
                    errors.append(f"Not a Python file: {file_path}")
                    continue

                # Check if file is readable
                if not os.access(path, os.R_OK):
                    errors.append(f"File is not readable: {file_path}")
                    continue

                # If we get here, the file path is valid
                valid_paths.append(str(path.resolve()))

            except Exception as e:
                errors.append(f"Error validating {file_path}: {e!s}")

        # Set output values
        self.parameter_output_values["valid_paths"] = valid_paths
        self.parameter_output_values["validation_errors"] = "\n".join(errors) if errors else ""

        # Also set in parameter_values for get_value compatibility
        self.parameter_values["valid_paths"] = valid_paths
        self.parameter_values["validation_errors"] = "\n".join(errors) if errors else ""
