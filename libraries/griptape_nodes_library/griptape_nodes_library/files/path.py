import re
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker

MAX_PADDING = 6
MIN_PADDING = 1


class FilePathComponents(DataNode):
    """Extract various components from a file path."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input parameter for the path
        self.path_input = ParameterString(
            name="path",
            default_value="",
            tooltip="The file path to extract components from.",
        )
        self.path_input.add_trait(
            FileSystemPicker(
                allow_files=True,
                allow_directories=True,
                multiple=False,
            )
        )
        self.add_parameter(self.path_input)

        # Add output parameters for path components
        self.add_parameter(
            ParameterString(
                name="filename",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The filename with extension, query parameters stripped (e.g., 'file.txt').",
                placeholder_text="Example: file.txt",
            )
        )

        self.add_parameter(
            ParameterString(
                name="stem",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The filename without extension (e.g., 'file').",
                placeholder_text="Example:file",
            )
        )

        # Add frame number output parameters
        self.add_parameter(
            Parameter(
                name="frame_number",
                output_type="int",
                type="int",
                allowed_modes={ParameterMode.OUTPUT},
                allow_input=False,
                allow_property=False,
                tooltip="Extracted frame number as integer (None if not found)",
            )
        )
        self.add_parameter(
            ParameterString(
                name="extension",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The file extension including the dot (e.g., '.txt').",
                placeholder_text="Example:.txt",
            )
        )

        self.add_parameter(
            ParameterString(
                name="parent",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The parent directory path.",
                placeholder_text="Example: /path/to/directory",
            )
        )

        self.add_parameter(
            ParameterString(
                name="parent_name",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The name of the immediate parent directory (e.g., 'directory').",
                placeholder_text="Example: directory",
            )
        )

        self.add_parameter(
            ParameterString(
                name="query_params",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The query parameters from the path (e.g., 't=123456').",
                placeholder_text="Example: t=123456",
            )
        )

        # Add padding parameter for frame number extraction
        with ParameterGroup(name="Frame Number Options", collapsed=True) as frame_options_group:
            ParameterInt(
                name="padding",
                default_value=4,
                tooltip="Number of digits for frame number padding (1-6)",
                allowed_modes={ParameterMode.PROPERTY},
                min_val=1,
                max_val=6,
            )
            ParameterString(
                name="frame_number_padded",
                allowed_modes={ParameterMode.OUTPUT},
                allow_input=False,
                allow_property=False,
                default_value="",
                placeholder_text="0001",
                tooltip="Extracted frame number as padded string (empty if not found)",
            )

        self.add_node_element(frame_options_group)

    def _extract_frame_number_from_filename(self, filename: str) -> tuple[int | None, re.Match[str] | None]:
        """Extract frame number from filename (e.g., extract.0001.jpg -> 1).

        Tries to find the longest sequence of digits, prioritizing 4+ digit sequences.

        Args:
            filename: Filename to extract from

        Returns:
            Tuple of (frame number as integer, or None if not found, match object for removal)
        """
        if not filename:
            return None, None

        # Try to find 4+ digit number pattern first (most common for frame sequences)
        match = re.search(r"(\d{4,})", filename)
        if match:
            try:
                frame_num = int(match.group(1))
            except (ValueError, TypeError):
                pass
            else:
                return frame_num, match

        # Try to find any number sequence
        match = re.search(r"(\d+)", filename)
        if match:
            try:
                frame_num = int(match.group(1))
            except (ValueError, TypeError):
                pass
            else:
                return frame_num, match

        return None, None

    def _remove_frame_number_from_stem(self, stem: str, frame_number: int | None, match: re.Match[str] | None) -> str:
        """Remove frame number pattern from stem.

        Args:
            stem: Stem to clean (filename without extension)
            frame_number: Extracted frame number (None if not found)
            match: Regex match object containing the frame number pattern

        Returns:
            Stem with frame number pattern removed
        """
        if frame_number is None or match is None:
            return stem

        # Get the matched string (e.g., "0001")
        matched_str = match.group(0)

        # Try to remove the frame number with common separators
        # Pattern 1: Remove with dot separator (e.g., "extract.0001" -> "extract")
        pattern_with_dot = re.escape(matched_str)
        stem = re.sub(rf"\.{pattern_with_dot}$", "", stem)
        stem = re.sub(rf"\.{pattern_with_dot}(?=\.|$)", "", stem)

        # Pattern 2: Remove with underscore separator (e.g., "extract_0001" -> "extract")
        stem = re.sub(rf"_{pattern_with_dot}$", "", stem)
        stem = re.sub(rf"_{pattern_with_dot}(?=\.|$)", "", stem)

        # Pattern 3: Remove without separator if at end (e.g., "extract0001" -> "extract")
        stem = stem.removesuffix(matched_str)

        return stem

    def _format_padded_frame_number(self, frame_number: int | None, padding: int) -> str:
        """Format frame number with padding.

        Args:
            frame_number: Frame number to pad (None if not found)
            padding: Number of digits for padding (1-6)

        Returns:
            Padded frame number as string, or empty string if frame_number is None
        """
        if frame_number is None:
            return ""

        # Ensure padding is within valid range
        padding = max(padding, MIN_PADDING)
        padding = min(padding, MAX_PADDING)

        return f"{frame_number:0{padding}d}"

    def _extract_path_components(self, path_str: str) -> None:
        """Extract path components and update output parameters."""
        # Initialize all outputs to empty strings
        filename = ""
        stem = ""
        extension = ""
        parent = ""
        parent_name = ""
        query_params = ""
        frame_number: int | None = None
        frame_number_padded = ""

        # Extract components if path is provided
        if path_str:
            # Split path and query parameters
            if "?" in path_str:
                path_part, query_part = path_str.split("?", 1)
                query_params = query_part
            else:
                path_part = path_str
                query_params = ""

            # Convert to Path object (without query params)
            path_obj = Path(path_part)

            # Extract components (without query params)
            filename = path_obj.name
            stem = path_obj.stem
            extension = path_obj.suffix
            parent = str(path_obj.parent) if path_obj.parent else ""
            parent_name = path_obj.parent.name if path_obj.parent else ""

            # Extract frame number from filename
            frame_number, frame_match = self._extract_frame_number_from_filename(filename)

            # Remove frame number from stem if found
            if frame_number is not None:
                stem = self._remove_frame_number_from_stem(stem, frame_number, frame_match)

        # Get padding value for frame number formatting
        padding = self.get_parameter_value("padding") or 4
        padding = max(padding, MIN_PADDING)
        padding = min(padding, MAX_PADDING)

        # Format padded frame number
        if frame_number is not None:
            frame_number_padded = self._format_padded_frame_number(frame_number, padding)

        # Set output values and publish updates
        self.parameter_output_values["filename"] = filename
        self.parameter_output_values["stem"] = stem
        self.parameter_output_values["extension"] = extension
        self.parameter_output_values["parent"] = parent
        self.parameter_output_values["parent_name"] = parent_name
        self.parameter_output_values["query_params"] = query_params
        self.parameter_output_values["frame_number"] = frame_number
        self.parameter_output_values["frame_number_padded"] = frame_number_padded

        self.publish_update_to_parameter("filename", filename)
        self.publish_update_to_parameter("stem", stem)
        self.publish_update_to_parameter("extension", extension)
        self.publish_update_to_parameter("parent", parent)
        self.publish_update_to_parameter("parent_name", parent_name)
        self.publish_update_to_parameter("query_params", query_params)
        self.publish_update_to_parameter("frame_number", frame_number)
        self.publish_update_to_parameter("frame_number_padded", frame_number_padded)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "path":
            # Convert value to string if needed
            if value is not None:
                path_str = str(value)
            else:
                path_str = ""

            # Clean path to remove newlines/carriage returns that cause Windows errors
            path_str = GriptapeNodes.OSManager().sanitize_path_string(path_str)

            self._extract_path_components(path_str)
        elif parameter.name == "padding":
            # Re-extract path components when padding changes to update padded frame number
            path_str = self.get_parameter_value("path")
            if path_str is not None:
                path_str = str(path_str)
            else:
                path_str = ""

            # Clean path to remove newlines/carriage returns that cause Windows errors
            path_str = GriptapeNodes.OSManager().sanitize_path_string(path_str)

            self._extract_path_components(path_str)

        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        pass

    def process(self) -> None:
        # Get the input path
        path_str = self.get_parameter_value("path")
        if path_str is not None:
            path_str = str(path_str)
        else:
            path_str = ""

            # Clean path to remove newlines/carriage returns that cause Windows errors
            path_str = GriptapeNodes.OSManager().sanitize_path_string(path_str)

        self._extract_path_components(path_str)
