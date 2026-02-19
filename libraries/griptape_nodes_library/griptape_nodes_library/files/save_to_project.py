from __future__ import annotations

from pathlib import Path
from typing import Any

from griptape.artifacts import UrlArtifact

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.events.os_events import (
    DeleteFileRequest,
    DeleteFileResultFailure,
    GetFileInfoRequest,
    GetFileInfoResultSuccess,
    RenameFileRequest,
    RenameFileResultFailure,
)
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes_library.files.file_operation_base import FileOperationBaseNode


class SaveToProject(FileOperationBaseNode):
    """Move a file into a project directory and output its macro path.

    Takes an absolute source path (e.g., from a Train LoRA node) and a destination
    that can be a macro path (e.g., {outputs}/loras) or a plain directory path.
    Moves the file to the resolved destination and outputs the macro form of the
    resulting path for use in subsequent nodes.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.source_path_param = Parameter(
            name="source_path",
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str", "UrlArtifact"],
            default_value="",
            tooltip="The absolute path of the file to save to the project.",
        )
        self.add_parameter(self.source_path_param)

        self.destination_param = Parameter(
            name="destination",
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str"],
            default_value="",
            tooltip="The project directory to save the file into. Accepts macro paths (e.g., {outputs}/loras) or absolute directory paths.",
            ui_options={"placeholder_text": "Enter destination directory or macro path"},
        )
        self.destination_param.add_trait(
            FileSystemPicker(
                allow_files=False,
                allow_directories=True,
            )
        )
        self.add_parameter(self.destination_param)

        self.overwrite_param = Parameter(
            name="overwrite",
            type="bool",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["bool"],
            default_value=False,
            tooltip="Whether to overwrite an existing file at the destination.",
        )
        self.add_parameter(self.overwrite_param)

        self.add_parameter(
            Parameter(
                name="saved_path",
                type="UrlArtifact",
                default_value=None,
                tooltip="The macro path of the saved file (e.g., {outputs}/loras/model.safetensors).",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self._create_status_parameters(
            result_details_tooltip="Details about the save result",
            result_details_placeholder="Details on the save attempt will be presented here.",
            parameter_group_initially_collapsed=True,
        )

    def process(self) -> None:
        """Execute the save-to-project operation."""
        self._clear_execution_status()

        source_path_raw = self.get_parameter_value("source_path") or ""
        destination_raw = self.get_parameter_value("destination") or ""
        overwrite = self.get_parameter_value("overwrite") or False

        source_path_str = self._extract_value_from_artifact(source_path_raw)
        source_path_str = GriptapeNodes.OSManager().sanitize_path_string(source_path_str)

        # FAILURE CASE: Empty source path
        if not source_path_str:
            msg = f"{self.name} attempted to save but source_path is empty."
            self.parameter_output_values["saved_path"] = None
            self._set_status_results(was_successful=False, result_details=msg)
            return

        destination_str = GriptapeNodes.OSManager().sanitize_path_string(destination_raw)

        # FAILURE CASE: Empty destination
        if not destination_str:
            msg = f"{self.name} attempted to save but destination is empty."
            self.parameter_output_values["saved_path"] = None
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # Resolve macro destination path to absolute path
        resolved_destination = self._resolve_destination_macro(destination_str)

        # FAILURE CASE: Macro resolution failed
        if resolved_destination is None:
            msg = f"{self.name} attempted to save but failed to resolve destination macro '{destination_str}'."
            self.parameter_output_values["saved_path"] = None
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # Determine the full destination file path (resolved_dir / source_filename)
        destination_file_path = self._resolve_destination_path(source_path_str, resolved_destination)

        # Handle overwrite: delete existing destination file if overwrite is True
        if overwrite:
            dest_info_result = GriptapeNodes.handle_request(
                GetFileInfoRequest(path=destination_file_path, workspace_only=False)
            )
            if isinstance(dest_info_result, GetFileInfoResultSuccess) and dest_info_result.file_entry is not None:
                delete_result = GriptapeNodes.handle_request(
                    DeleteFileRequest(path=destination_file_path, workspace_only=False)
                )
                if isinstance(delete_result, DeleteFileResultFailure):
                    failure_reason = (
                        delete_result.failure_reason.value
                        if hasattr(delete_result.failure_reason, "value")
                        else "Unknown error"
                    )
                    msg = f"{self.name} attempted to overwrite '{destination_file_path}' but deletion failed: {failure_reason}"
                    self.parameter_output_values["saved_path"] = None
                    self._set_status_results(was_successful=False, result_details=msg)
                    return

        # Move the source file to the resolved destination
        rename_result = GriptapeNodes.handle_request(
            RenameFileRequest(
                old_path=source_path_str,
                new_path=destination_file_path,
                workspace_only=False,
            )
        )

        # FAILURE CASE: Move failed
        if isinstance(rename_result, RenameFileResultFailure):
            failure_reason = (
                rename_result.failure_reason.value
                if hasattr(rename_result.failure_reason, "value")
                else "Unknown error"
            )
            error_details = f" - {rename_result.result_details}" if rename_result.result_details else ""
            msg = f"{self.name} attempted to save '{source_path_str}' to '{destination_file_path}'. Failed: {failure_reason}{error_details}"
            self.parameter_output_values["saved_path"] = None
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # Map the absolute destination path back to macro form
        saved_path_str = self._map_to_macro_path(destination_file_path)

        # SUCCESS PATH AT END
        saved_path_artifact = UrlArtifact(saved_path_str)
        self.set_parameter_value("saved_path", saved_path_artifact)
        self.parameter_output_values["saved_path"] = saved_path_artifact

        msg = f"Saved '{source_path_str}' → '{saved_path_str}'"
        self._set_status_results(was_successful=True, result_details=msg)

    def _resolve_destination_macro(self, destination: str) -> str | None:
        """Resolve a macro path (e.g., {outputs}/loras) to its absolute filesystem path.

        Returns the absolute path string, or None if macro resolution fails.
        Plain paths without macro variables are returned as-is.
        """
        try:
            parsed = ParsedMacro(destination)
        except MacroSyntaxError:
            # Not valid macro syntax - treat as a plain path
            return destination

        if not parsed.get_variables():
            # No macro variables - it's a plain path
            return destination

        result = GriptapeNodes.handle_request(GetPathForMacroRequest(parsed_macro=parsed, variables={}))

        if isinstance(result, GetPathForMacroResultSuccess):
            return str(result.absolute_path)

        return None

    def _map_to_macro_path(self, absolute_path: str) -> str:
        """Map an absolute path back to its macro form if it lies within a project directory.

        Returns the macro path (e.g., {outputs}/loras/model.safetensors) if the path
        is inside a project directory, otherwise returns the absolute path unchanged.
        """
        result = GriptapeNodes.handle_request(AttemptMapAbsolutePathToProjectRequest(absolute_path=Path(absolute_path)))

        if isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess) and result.mapped_path is not None:
            return result.mapped_path

        return absolute_path
