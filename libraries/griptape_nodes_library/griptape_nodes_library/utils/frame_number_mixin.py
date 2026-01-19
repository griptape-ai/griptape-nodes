"""Mixin for adding frame number padding functionality to nodes."""

from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options


class FrameNumberMixin:
    """Mixin that provides frame number padding functionality to nodes.

    This mixin adds:
    - add_frame_number: Boolean to enable frame number insertion
    - frame_number: Integer frame number to insert
    - padding: Integer padding width (1-6, default 4)
    - separator: String separator ('.' or '_', default '.')

    Usage:
        class MyNode(FrameNumberMixin, BaseNode):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self._add_frame_number_parameters()
    """

    def _add_frame_number_parameters(self) -> None:
        """Add frame number parameters to the node."""
        # Add frame number parameter
        self.add_frame_number = ParameterBool(
            name="add_frame_number",
            default_value=False,
            tooltip="If enabled, insert a padded frame number into the filename (replaces #### pattern or inserts before extension)",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.add_frame_number)

        # Frame number parameter (hidden by default)
        self.frame_number = ParameterInt(
            name="frame_number",
            default_value=1,
            tooltip="Frame number to insert into filename",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            hide=True,
        )
        self.add_parameter(self.frame_number)

        # Padding parameter (hidden by default)
        self.padding = ParameterInt(
            name="padding",
            default_value=4,
            tooltip="Number of digits for frame number padding (1-6)",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            min_val=1,
            max_val=6,
            hide=True,
        )
        self.add_parameter(self.padding)

        # Separator parameter (hidden by default)
        self.separator = ParameterString(
            name="separator",
            default_value=".",
            tooltip="Separator to use when inserting frame number (dot or underscore)",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            traits={Options(choices=[".", "_"])},
            hide=True,
        )
        self.add_parameter(self.separator)

    def _handle_frame_number_parameter_change(self, parameter: Parameter, value: Any) -> None:
        """Handle frame number parameter visibility changes.

        Call this from your node's after_value_set method.

        Args:
            parameter: The parameter that changed
            value: The new value
        """
        if parameter.name == "add_frame_number":
            if value:
                self.show_parameter_by_name("frame_number")
                self.show_parameter_by_name("padding")
                self.show_parameter_by_name("separator")
            else:
                self.hide_parameter_by_name("frame_number")
                self.hide_parameter_by_name("padding")
                self.hide_parameter_by_name("separator")

    def _insert_frame_number(self, filename: str, frame_number: int | None = None, padding: int | None = None, separator: str | None = None) -> str:
        """Insert padded frame number into filename.

        If filename contains #### pattern, replace it with padded number.
        Otherwise, insert padded number before the file extension using the specified separator.

        Args:
            filename: Filename or path
            frame_number: Frame number to insert (if None, gets from parameter)
            padding: Number of digits for padding (1-6, if None, gets from parameter)
            separator: Separator to use ('.' or '_', if None, gets from parameter)

        Returns:
            Filename with frame number inserted
        """
        # Get values from parameters if not provided
        if frame_number is None:
            frame_number = self.get_parameter_value("frame_number") or 1
        if padding is None:
            padding = self.get_parameter_value("padding") or 4
        if separator is None:
            separator = self.get_parameter_value("separator") or "."

        # Ensure padding is between 1 and 6, and separator is valid
        padding = max(1, min(6, int(padding)))
        if separator not in [".", "_"]:
            separator = "."

        path_obj = Path(filename)

        # Get stem and extension
        stem = path_obj.stem
        extension = path_obj.suffix
        parent = path_obj.parent

        # Check if stem contains #### pattern
        if "####" in stem:
            # Replace #### with padded frame number
            padded_number = f"{frame_number:0{padding}d}"
            new_stem = stem.replace("####", padded_number)
        else:
            # Insert padded frame number before extension using specified separator
            padded_number = f"{frame_number:0{padding}d}"
            new_stem = f"{stem}{separator}{padded_number}"

        # Reconstruct path
        if parent and str(parent) != ".":
            return str(parent / f"{new_stem}{extension}")
        return f"{new_stem}{extension}"

    def _apply_frame_number_if_enabled(self, filename: str) -> str:
        """Apply frame number insertion if enabled.

        Convenience method that checks if add_frame_number is enabled and applies it.

        Args:
            filename: Filename or path

        Returns:
            Filename with frame number inserted if enabled, otherwise original filename
        """
        add_frame_number = self.get_parameter_value("add_frame_number") or False
        if add_frame_number:
            return self._insert_frame_number(filename)
        return filename

