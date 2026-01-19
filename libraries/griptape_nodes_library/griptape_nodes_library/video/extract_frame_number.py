"""Extract frame number from filename."""

import re
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString

__all__ = ["ExtractFrameNumber"]


class ExtractFrameNumber(DataNode):
    """Extract frame number from a filename.

    Inputs:
        - filename (str): Filename or path to extract frame number from (required)
        - padding (int): Number of digits for padding (1-6, default: 4)

    Outputs:
        - frame_number (int): Extracted frame number as integer (None if not found)
        - frame_number_padded (str): Extracted frame number as padded string (empty if not found)
    """

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input filename parameter
        self.add_parameter(
            ParameterString(
                name="filename",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                placeholder_text="extract.0001.jpg",
                tooltip="Filename or path to extract frame number from",
            )
        )

        # Add padding parameter
        with ParameterGroup(name="Options") as options_group:
            ParameterInt(
                name="padding",
                default_value=4,
                tooltip="Number of digits for padding (1-6)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                min_val=1,
                max_val=6,
            )

        self.add_node_element(options_group)

        # Add output parameters
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
                name="frame_number_padded",
                allowed_modes={ParameterMode.OUTPUT},
                allow_input=False,
                allow_property=False,
                placeholder_text="0001",
                tooltip="Extracted frame number as padded string (empty if not found)",
            )
        )

    def _extract_frame_number_from_filename(self, filename: str) -> int | None:
        """Extract frame number from filename (e.g., extract.0001.jpg -> 1).

        Tries to find the longest sequence of digits, prioritizing 4+ digit sequences.

        Args:
            filename: Filename or path to extract from

        Returns:
            Frame number as integer, or None if not found
        """
        if not filename:
            return None

        # Extract just the filename if a path is provided
        path_obj = Path(filename)
        filename_only = path_obj.name

        # Try to find 4+ digit number pattern first (most common for frame sequences)
        match = re.search(r"(\d{4,})", filename_only)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass

        # Try to find any number sequence
        match = re.search(r"(\d+)", filename_only)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass

        return None

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
        if padding < 1:
            padding = 1
        if padding > 6:
            padding = 6

        return f"{frame_number:0{padding}d}"

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name not in ["frame_number", "frame_number_padded"]:
            self._update_outputs()
        return super().after_value_set(parameter, value)

    def _update_outputs(self) -> None:
        """Update output parameters with extracted frame number."""
        filename = self.get_parameter_value("filename") or ""
        padding = self.get_parameter_value("padding") or 4

        # Ensure padding is within valid range
        if padding < 1:
            padding = 1
        if padding > 6:
            padding = 6

        frame_number = self._extract_frame_number_from_filename(filename)
        frame_number_padded = self._format_padded_frame_number(frame_number, padding)

        self.parameter_output_values["frame_number"] = frame_number
        self.parameter_output_values["frame_number_padded"] = frame_number_padded

    def process(self) -> None:
        """Process the extraction and set output values."""
        self._update_outputs()

