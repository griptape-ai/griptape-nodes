from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.param_components.progress_bar_component import ProgressBarComponent
from griptape_nodes.retained_mode.events.os_events import (
    CopyFileRequest,
    CopyFileResultFailure,
    CopyTreeRequest,
    CopyTreeResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes_library.files.file_operation_base import BaseFileOperationInfo, FileOperationBaseNode

logger = logging.getLogger(__name__)


class CopyStatus(Enum):
    """Status of a copy attempt."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    INVALID = "invalid"  # Invalid or inaccessible path


@dataclass
class CopyFileInfo(BaseFileOperationInfo):
    """Information about a file/directory copy attempt."""

    status: CopyStatus = CopyStatus.PENDING
    copied_paths: list[str] = field(default_factory=list)  # Paths actually copied (from OS result)


class CopyFiles(FileOperationBaseNode):
    """Copy files and/or directories from source to destination.

    Directories are copied recursively with all their contents.
    Accepts single path (str) or multiple paths (list[str]) for source_paths.
    Supports glob patterns (e.g., "/path/to/*.txt") for matching multiple files.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Define converter function for extracting artifact values
        def convert_artifact_to_string(value: Any) -> Any:
            """Converter function to extract string values from artifacts."""
            # If already a string, return as-is to avoid recursion
            if isinstance(value, str):
                return value
            # If None or empty, return as-is
            if value is None:
                return None
            # Extract from artifact
            return self._extract_artifacts_from_value(value)

        # Input parameter - accepts any type, will be normalized to list[str]
        self.source_paths = ParameterList(
            name="source_paths",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str", "list", "any"],
            default_value=[],
            tooltip="Path(s) to file(s) or directory(ies) to copy. Supports glob patterns (e.g., '/path/*.txt').",
            converters=[convert_artifact_to_string],
        )
        self.add_parameter(self.source_paths)

        # Destination directory parameter
        self.destination_path = Parameter(
            name="destination_path",
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str"],
            default_value="",
            tooltip="Destination directory where files will be copied.",
            ui_options={"placeholder_text": "Enter destination directory path"},
        )
        self.destination_path.add_trait(
            FileSystemPicker(
                allow_files=False,
                allow_directories=True,
                multiple=False,
            )
        )
        self.add_parameter(self.destination_path)

        # Overwrite parameter
        self.overwrite = Parameter(
            name="overwrite",
            type="bool",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["bool"],
            default_value=False,
            tooltip="Whether to overwrite existing files at destination (default: False).",
        )
        self.add_parameter(self.overwrite)

        # Output parameter
        self.copied_paths_output = Parameter(
            name="copied_paths",
            allow_input=False,
            allow_property=False,
            output_type="list[str]",
            default_value=[],
            tooltip="List of all destination paths that were copied successfully.",
        )
        self.add_parameter(self.copied_paths_output)

        # Create progress bar component
        self.progress_component = ProgressBarComponent(self)
        self.progress_component.add_property_parameters()

        # Create status parameters
        self._create_status_parameters(
            result_details_tooltip="Details about the copy result",
            result_details_placeholder="Details on the copy attempt will be presented here.",
            parameter_group_initially_collapsed=True,
        )

    def _execute_copy(self, target: CopyFileInfo, destination_dir: str, *, overwrite: bool) -> None:
        """Execute copy operation for a single target.

        Args:
            target: CopyFileInfo with source_path set
            destination_dir: Destination directory
            overwrite: Whether to overwrite existing files
        """
        # Resolve destination path
        destination_path = self._resolve_destination_path(target.source_path, destination_dir)
        target.destination_path = destination_path

        # Log the operation attempt for better error context
        operation_type = "directory" if target.is_directory else "file"
        logger.info(
            "%s: Attempting to copy %s '%s' to '%s'",
            self.name,
            operation_type,
            target.source_path,
            destination_path,
        )

        # Check if source is a file or directory
        if target.is_directory:
            # Use CopyTreeRequest for directories
            request = CopyTreeRequest(
                source_path=target.source_path,
                destination_path=destination_path,
                dirs_exist_ok=overwrite,
            )
            result = GriptapeNodes.handle_request(request)

            if isinstance(result, CopyTreeResultFailure):
                target.status = CopyStatus.FAILED
                # Include context about what was being copied
                failure_reason = (
                    result.failure_reason.value if hasattr(result.failure_reason, "value") else "Unknown error"
                )
                failure_msg = f"{self.name}: Failed to copy directory '{target.source_path}' to '{destination_path}': {failure_reason}"
                logger.error(failure_msg)
                target.failure_reason = failure_msg
                return

            # SUCCESS PATH AT END
            target.status = CopyStatus.SUCCESS
            # For directories, we track the destination path
            target.copied_paths = [destination_path]
        else:
            # Use CopyFileRequest for files
            request = CopyFileRequest(
                source_path=target.source_path,
                destination_path=destination_path,
                overwrite=overwrite,
            )
            result = GriptapeNodes.handle_request(request)

            if isinstance(result, CopyFileResultFailure):
                target.status = CopyStatus.FAILED
                # Include context about what was being copied
                failure_reason = (
                    result.failure_reason.value if hasattr(result.failure_reason, "value") else "Unknown error"
                )
                failure_msg = (
                    f"{self.name}: Failed to copy file '{target.source_path}' to '{destination_path}': {failure_reason}"
                )
                logger.error(failure_msg)
                target.failure_reason = failure_msg
                return

            # SUCCESS PATH AT END
            target.status = CopyStatus.SUCCESS
            target.copied_paths = [destination_path]

    def _format_result_details(self, all_targets: list[CopyFileInfo]) -> str:
        """Format detailed results showing what happened to each file."""
        lines = []

        # Count outcomes
        succeeded = [t for t in all_targets if t.status == CopyStatus.SUCCESS]
        failed = [t for t in all_targets if t.status == CopyStatus.FAILED]
        invalid = [t for t in all_targets if t.status == CopyStatus.INVALID]

        # Summary line
        valid_targets = [t for t in all_targets if t.status != CopyStatus.INVALID]
        lines.append(f"Copied {len(succeeded)}/{len(valid_targets)} valid items")

        # Show failures if any
        if failed:
            lines.append(f"\nFailed to copy ({len(failed)}):")
            for target in failed:
                reason = target.failure_reason or "Unknown error"
                lines.append(f"  ❌ {target.source_path}: {reason}")

        # Show invalid paths if any
        if invalid:
            lines.append(f"\nInvalid paths ({len(invalid)}):")
            for target in invalid:
                reason = target.failure_reason or "Invalid or inaccessible"
                lines.append(f"  ⚠️ {target.source_path}: {reason}")

        # Show successfully copied files
        if succeeded:
            lines.append(f"\nSuccessfully copied ({len(succeeded)}):")
            for target in succeeded:
                if target.is_directory:
                    lines.append(f"  📁 {target.source_path} → {target.destination_path}")
                else:
                    lines.append(f"  📄 {target.source_path} → {target.destination_path}")

        return "\n".join(lines)

    def process(self) -> None:
        """Execute the file copy operation."""
        self._clear_execution_status()
        self.progress_component.reset()

        # Get parameter values
        source_paths_raw = self.get_parameter_list_value("source_paths")
        destination_dir = self.get_parameter_value("destination_path")
        overwrite = self.get_parameter_value("overwrite") or False

        # Handle empty paths as success with info message (consistent with delete_file)
        if not source_paths_raw:
            msg = "No files specified for copying"
            self.set_parameter_value(self.copied_paths_output.name, [])
            self._set_status_results(was_successful=True, result_details=msg)
            return

        # Normalize to list of strings (get_parameter_list_value flattens, but we need to ensure strings)
        # Also extract values from artifacts
        source_paths = [self._extract_value_from_artifact(p) for p in source_paths_raw if p is not None]

        # Remove duplicates
        source_paths = list(set(source_paths))

        # FAILURE CASE: Empty destination
        if not destination_dir:
            msg = f"{self.name} attempted to copy but destination path is empty. Failed due to no destination provided"
            self.set_parameter_value(self.copied_paths_output.name, [])
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # Determine if destination is a directory or file path
        # We'll validate this per-file in _resolve_destination_path
        # For now, just proceed with copy operations

        # Collect all targets (includes INVALID status for bad paths)
        all_targets = self._collect_all_files(
            paths=source_paths,
            info_class=CopyFileInfo,
            pending_status=CopyStatus.PENDING,
            invalid_status=CopyStatus.INVALID,
        )

        # Separate valid and invalid targets
        pending_targets = [t for t in all_targets if t.status == CopyStatus.PENDING]

        # FAILURE CASE: No valid targets at all
        if not pending_targets:
            msg = f"{self.name} attempted to copy but all source paths were invalid. No files copied"
            details = self._format_result_details(all_targets)
            self.set_parameter_value(self.copied_paths_output.name, [])
            self._set_status_results(was_successful=False, result_details=f"{msg}\n\n{details}")
            return

        # Check if destination looks like a file path (has extension)
        destination_path_obj = Path(destination_dir)
        destination_is_file_path = bool(destination_path_obj.suffix)

        # FAILURE CASE: Multiple source files but destination is a file path
        if destination_is_file_path and len(pending_targets) > 1:
            msg = f"{self.name} attempted to copy {len(pending_targets)} files to a single file path '{destination_dir}'. Cannot copy multiple files to a single file destination. Use a directory path instead."
            self.set_parameter_value(self.copied_paths_output.name, [])
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # Execute copies for all explicitly requested items
        explicitly_requested = [t for t in pending_targets if t.explicitly_requested]

        # Initialize progress bar with total number of files to copy
        self.progress_component.initialize(len(explicitly_requested))

        for target in explicitly_requested:
            self._execute_copy(target, destination_dir, overwrite=overwrite)
            # Increment progress after each file is processed
            self.progress_component.increment()

        # Collect all successfully copied paths
        all_copied_paths: list[str] = []
        for target in explicitly_requested:
            if target.status == CopyStatus.SUCCESS:
                all_copied_paths.extend(target.copied_paths)

        # Only report on explicitly requested items
        requested_targets = [t for t in all_targets if t.explicitly_requested]

        # Determine success/failure
        succeeded_count = len([t for t in requested_targets if t.status == CopyStatus.SUCCESS])

        # FAILURE CASE: Zero files were successfully copied
        if succeeded_count == 0:
            msg = f"{self.name} failed to copy any files"
            details = self._format_result_details(requested_targets)
            self.set_parameter_value(self.copied_paths_output.name, [])
            self._set_status_results(was_successful=False, result_details=f"{msg}\n\n{details}")
            return

        # SUCCESS PATH AT END (even if some failed, as long as at least one succeeded)
        # Set output parameters
        self.set_parameter_value(self.copied_paths_output.name, all_copied_paths)
        self.parameter_output_values[self.copied_paths_output.name] = all_copied_paths

        # Generate detailed result message (only for explicitly requested items)
        details = self._format_result_details(requested_targets)

        self._set_status_results(was_successful=True, result_details=details)
