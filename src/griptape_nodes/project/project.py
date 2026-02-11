"""Project file operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.os_manager import OSManager

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.file.file_loader import FileLoader
from griptape_nodes.project.types import (
    ExistingFilePolicy,
    SaveRequest,
    SaveResult,
)
from griptape_nodes.retained_mode.events.os_events import (
    DryRunWriteFileRequest,
    WriteFileRequest,
    WriteFileResultDryRun,
    WriteFileResultFailure,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy as OSExistingFilePolicy,
)
from griptape_nodes.retained_mode.events.project_events import (
    GetCurrentProjectRequest,
    MacroPath,
)
from griptape_nodes.retained_mode.managers.image_metadata_injector import (
    inject_workflow_metadata_if_image,
)
from griptape_nodes.utils.path_utils import resolve_workspace_path


@dataclass
class Project:
    """Project-aware file operations.

    Provides simple API for saving and loading files with:
    - Macro template resolution ({outputs}/{name}_{_index}.png)
    - Collision policies (CREATE_NEW, OVERWRITE, FAIL)
    - Automatic workflow metadata injection (PNG files)
    - Multi-backend loading (HTTP, S3, cloud, local, data URIs)

    Save responsibilities:
    - Inject workflow metadata into images
    - Delegate to OSManager for:
      - Macro resolution to absolute paths
      - Collision policies (CREATE_NEW, OVERWRITE, FAIL)
      - Auto-increment {_index} variable when needed
      - Create parent directories
      - Atomic file writing

    Load responsibilities:
    - Optional macro resolution
    - Coordinate with File for actual I/O

    Does NOT know about:
    - Situations (that's ProjectFileParameter's job)
    - UI (that's ProjectFileParameter's job)

    Usage:
        project = GriptapeNodes.Project()
        result = await project.save(SaveRequest(...))
    """

    os_manager: OSManager  # Injected dependency

    async def save(self, request: SaveRequest) -> SaveResult:
        """Save file using project configuration.

        Flow:
        1. Inject workflow metadata if image (before OSManager call)
        2. Create MacroPath from template + variables
        3. Map policy to OSManager enum
        4. Call OSManager.on_write_file_request() with CREATE_NEW/OVERWRITE/FAIL policy
        5. OSManager handles: macro resolution, collision detection, parent dirs, atomic write
        6. Extract final path and index from result

        Args:
            request: SaveRequest with data, template, variables, policy

        Returns:
            SaveResult with path, url, and index_used

        Raises:
            FileExistsError: File exists and policy is FAIL
            MacroResolutionError: Missing required variables
            OSError: Cannot create parent directory or write file
        """
        # 1. Inject metadata BEFORE calling OSManager (metadata uses filename extension for format detection)
        data_to_write = inject_workflow_metadata_if_image(
            data=request.data,
            file_name=request.macro_template,  # Uses template for extension detection
        )

        # 2. Create MacroPath for OSManager
        parsed_macro = ParsedMacro(request.macro_template)
        macro_path = MacroPath(parsed_macro=parsed_macro, variables=request.variables)

        # 3. Map policy to OSManager enum
        policy_map = {
            ExistingFilePolicy.CREATE_NEW: OSExistingFilePolicy.CREATE_NEW,
            ExistingFilePolicy.OVERWRITE: OSExistingFilePolicy.OVERWRITE,
            ExistingFilePolicy.FAIL: OSExistingFilePolicy.FAIL,
        }
        os_policy = policy_map[request.policy]

        # 4. Create WriteFileRequest
        write_request = WriteFileRequest(
            file_path=macro_path,
            content=data_to_write,
            encoding="utf-8",
            existing_file_policy=os_policy,
            create_parents=request.create_dirs,
        )

        # 5. Execute via OSManager
        result = self.os_manager.on_write_file_request(write_request)

        # 6. Handle result
        if isinstance(result, WriteFileResultFailure):
            msg = f"Failed to write file: {result.result_details}"
            raise OSError(msg)

        if not isinstance(result, WriteFileResultSuccess):
            msg = f"Unexpected result type: {type(result)}"
            raise OSError(msg)

        # 7. Extract details
        final_path = Path(result.final_file_path)

        # 8. Determine index used (extract from final path vs template if CREATE_NEW policy used)
        index_used = None
        if request.policy == ExistingFilePolicy.CREATE_NEW:
            index_used = self._extract_index_from_result(
                final_path=final_path,
                macro_template=request.macro_template,
            )

        # 9. Return result
        return SaveResult(
            path=final_path,
            url=str(final_path),  # For local files, URL is same as path
            index_used=index_used,
        )

    async def load(self, location: str | Any, timeout: float = 120.0) -> bytes:  # noqa: ASYNC109
        """Load file from any location.

        Supports:
        - Macros: "{outputs}/file.png" → resolves then loads
        - Absolute paths: "/workspace/outputs/file.png" → loads directly
        - URLs: "https://example.com/image.png" → downloads
        - S3: "s3://bucket/key" → downloads
        - Data URIs: "data:image/png;base64,..." → decodes
        - Artifacts: ImageArtifact, ImageUrlArtifact → extracts location from .value

        Args:
            location: Location string (any format) or artifact with .value attribute
            timeout: Timeout for read operation (passed to underlying driver)

        Returns:
            File contents as bytes
        """
        # Handle artifacts (ImageArtifact, ImageUrlArtifact, etc.)
        if hasattr(location, "value"):
            location = location.value

        # Convert to string if not already
        location = str(location)

        # Resolve macro if present (use simple resolution with empty variables)
        if "{" in location:
            location = self._resolve_macro_for_load(location)

        # Load using FileLoader
        file = FileLoader(location=location)
        return await file.read(timeout)

    async def preview_save(self, request: SaveRequest) -> SaveResult:
        """Preview what would happen during save without actually writing.

        Performs all steps except the actual file write:
        - Resolves macro to absolute path
        - Applies collision policy (finds next available index if needed)
        - Shows what the final path would be
        - Does NOT create directories or write file

        Args:
            request: SaveRequest to preview

        Returns:
            SaveResult with path and metadata (no file written)
        """
        # Create MacroPath for OSManager
        parsed_macro = ParsedMacro(request.macro_template)
        macro_path = MacroPath(parsed_macro=parsed_macro, variables=request.variables)

        # Map policy to OSManager enum
        policy_map = {
            ExistingFilePolicy.CREATE_NEW: OSExistingFilePolicy.CREATE_NEW,
            ExistingFilePolicy.OVERWRITE: OSExistingFilePolicy.OVERWRITE,
            ExistingFilePolicy.FAIL: OSExistingFilePolicy.FAIL,
        }
        os_policy = policy_map[request.policy]

        # Create DryRunWriteFileRequest
        dry_run_request = DryRunWriteFileRequest(
            file_path=macro_path,
            content=request.data,
            encoding="utf-8",
            existing_file_policy=os_policy,
            create_parents=request.create_dirs,
        )

        # Execute via OSManager
        result = self.os_manager.on_dry_run_write_file_request(dry_run_request)

        if not isinstance(result, WriteFileResultDryRun):
            msg = f"Unexpected result type: {type(result)}"
            raise OSError(msg)

        # Extract preview result
        final_path = Path(result.would_write_to_path)
        index_used = result.index_that_would_be_used

        return SaveResult(
            path=final_path,
            url=str(final_path),
            index_used=index_used,
        )

    def _extract_index_from_result(
        self,
        final_path: Path,
        macro_template: str,
    ) -> int | None:
        """Extract the index value used from the final path.

        When CREATE_NEW policy is used, OSManager may have incremented an index variable
        to find the next available filename. This method attempts to extract that index
        value from the final path using simple heuristics.

        Args:
            final_path: The actual path where the file was written
            macro_template: The original macro template

        Returns:
            The index value used, or None if no index was found or couldn't be determined
        """
        # Look for optional index variables in the template
        try:
            parsed = ParsedMacro(macro_template)
            variable_infos = parsed.get_variables()

            # Find optional variables with "index" in the name
            for var_info in variable_infos:
                if not var_info.is_required and "index" in var_info.name.lower():
                    # Try to extract the index from the final path
                    # This is a simple heuristic - we look for numbers in the filename
                    # Get the filename without extension
                    stem = final_path.stem

                    # Look for numbers at the end (common pattern: file_001, file_002, etc.)
                    match = re.search(r"_(\d+)$", stem)
                    if match:
                        return int(match.group(1))

                    # If not found at end, try to find any number
                    match = re.search(r"(\d+)", stem)
                    if match:
                        return int(match.group(1))

        except Exception:
            # If anything fails, just return None
            return None

        return None

    def _get_builtin_resolution_bag(
        self,
        variable_infos: list,
        project_info: Any,
    ) -> dict[str, str | int]:
        """Get builtin variable resolution bag from project info.

        Args:
            variable_infos: List of variable info from parsed macro
            project_info: Project info from ProjectManager

        Returns:
            Dictionary mapping variable names to their resolved values
        """
        resolution_bag: dict[str, str | int] = {}
        template = project_info.template

        for var_info in variable_infos:
            var_name = var_info.name

            # Map builtin variables
            if var_name in {"project_dir", "workspace_dir"}:
                resolution_bag[var_name] = str(project_info.project_base_dir)
            elif var_name == "workflow_name":
                resolution_bag[var_name] = project_info.workflow_name or "workflow"
            elif var_name == "outputs":
                if "outputs" in template.directories:
                    resolution_bag[var_name] = template.directories["outputs"].path_macro
                else:
                    resolution_bag[var_name] = "outputs"
            elif var_name == "inputs":
                if "inputs" in template.directories:
                    resolution_bag[var_name] = template.directories["inputs"].path_macro
                else:
                    resolution_bag[var_name] = "inputs"

        return resolution_bag

    def _resolve_macro_for_load(self, location: str) -> str:
        """Resolve macro in location string for load operations.

        This is a simplified macro resolution for load operations. It only resolves
        builtin variables like {outputs}, {workspace_dir}, etc. User-provided variables
        are not supported in load operations (they should be resolved before calling load).

        Args:
            location: Location string with macros

        Returns:
            Resolved location string

        Raises:
            MacroResolutionError: If required variables are missing or resolution fails
        """
        # Import here to avoid circular import
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Parse macro and get project info
        parsed_macro = ParsedMacro(location)
        variable_infos = parsed_macro.get_variables()
        project_manager = GriptapeNodes.ProjectManager()
        result = project_manager.on_get_current_project_request(GetCurrentProjectRequest())

        if not hasattr(result, "project_info"):
            msg = "No current project set - cannot resolve macros for load"
            raise RuntimeError(msg)

        project_info = result.project_info

        # Build resolution bag with builtin variables
        resolution_bag = self._get_builtin_resolution_bag(variable_infos, project_info)

        # Resolve macro
        secrets_manager = project_manager._secrets_manager
        if secrets_manager is None:
            msg = "SecretsManager not available for macro resolution"
            raise RuntimeError(msg)

        resolved_string = parsed_macro.resolve(resolution_bag, secrets_manager)

        # Convert to absolute path if needed
        resolved_path = Path(resolved_string)
        if not resolved_path.is_absolute():
            project_base_dir = project_info.project_base_dir
            resolved_path = resolve_workspace_path(resolved_path, project_base_dir)

        return str(resolved_path)
