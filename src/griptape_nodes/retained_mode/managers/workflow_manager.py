from __future__ import annotations

import ast
import logging
import pickle
import pkgutil
import re
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, TypeVar, cast

import tomlkit
from rich.box import HEAVY_EDGE
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.node_library.library_registry import LibraryNameAndVersion
from griptape_nodes.node_library.workflow_registry import (
    WorkflowMetadata,
    WorkflowRegistry,
)
from griptape_nodes.retained_mode.events.app_events import (
    GetEngineVersionRequest,
    GetEngineVersionResultSuccess,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
    SerializedFlowCommands,
    SerializedNodeCommands,
    SerializeFlowToCommandsRequest,
    SerializeFlowToCommandsResultFailure,
    SerializeFlowToCommandsResultSuccess,
)
from griptape_nodes.retained_mode.events.library_events import (
    GetLibraryMetadataRequest,
    GetLibraryMetadataResultSuccess,
    ListRegisteredLibrariesRequest,
    ListRegisteredLibrariesResultSuccess,
    UnloadLibraryFromRegistryRequest,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
)
from griptape_nodes.retained_mode.events.object_events import (
    ClearAllObjectStateRequest,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    DeleteWorkflowRequest,
    DeleteWorkflowResultFailure,
    DeleteWorkflowResultSuccess,
    ListAllWorkflowsRequest,
    ListAllWorkflowsResultFailure,
    ListAllWorkflowsResultSuccess,
    LoadWorkflowMetadata,
    LoadWorkflowMetadataResultFailure,
    LoadWorkflowMetadataResultSuccess,
    RegisterWorkflowRequest,
    RegisterWorkflowResultFailure,
    RegisterWorkflowResultSuccess,
    RenameWorkflowRequest,
    RenameWorkflowResultFailure,
    RenameWorkflowResultSuccess,
    RunWorkflowFromRegistryRequest,
    RunWorkflowFromRegistryResultFailure,
    RunWorkflowFromRegistryResultSuccess,
    RunWorkflowFromScratchRequest,
    RunWorkflowFromScratchResultFailure,
    RunWorkflowFromScratchResultSuccess,
    RunWorkflowWithCurrentStateRequest,
    RunWorkflowWithCurrentStateResultFailure,
    RunWorkflowWithCurrentStateResultSuccess,
    SaveWorkflowRequest,
    SaveWorkflowResultFailure,
    SaveWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import (
    GriptapeNodes,
    Version,
    handle_flow_saving,
    handle_parameter_creation_saving,
)

if TYPE_CHECKING:
    from types import TracebackType

    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager


T = TypeVar("T")


logger = logging.getLogger("griptape_nodes")


class WorkflowManager:
    WORKFLOW_METADATA_HEADER: ClassVar[str] = "script"
    MAX_MINOR_VERSION_DEVIATION: ClassVar[int] = 2
    EPOCH_START = datetime(tzinfo=UTC, year=1970, month=1, day=1)

    class WorkflowStatus(StrEnum):
        """The status of a workflow that was attempted to be loaded."""

        GOOD = "GOOD"  # No errors detected during loading. Registered.
        FLAWED = "FLAWED"  # Some errors detected, but recoverable. Registered.
        UNUSABLE = "UNUSABLE"  # Errors detected and not recoverable. Not registered.
        MISSING = "MISSING"  # File not found. Not registered.

    class WorkflowDependencyStatus(StrEnum):
        """Records the status of each dependency for a workflow that was attempted to be loaded."""

        PERFECT = "PERFECT"  # Same major, minor, and patch version
        GOOD = "GOOD"  # Same major, minor version
        CAUTION = "CAUTION"  # Dependency is ahead within maximum minor revisions
        BAD = "BAD"  # Different major, or dependency ahead by more than maximum minor revisions
        MISSING = "MISSING"  # Not found
        UNKNOWN = "UNKNOWN"  # May not have been able to evaluate due to other errors.

    @dataclass
    class WorkflowDependencyInfo:
        """Information about each dependency in a workflow that was attempted to be loaded."""

        library_name: str
        version_requested: str
        version_present: str | None
        status: WorkflowManager.WorkflowDependencyStatus

    @dataclass
    class WorkflowInfo:
        """Information about a workflow that was attempted to be loaded."""

        status: WorkflowManager.WorkflowStatus
        workflow_path: str
        workflow_name: str | None = None
        workflow_dependencies: list[WorkflowManager.WorkflowDependencyInfo] = field(default_factory=list)
        problems: list[str] = field(default_factory=list)

    _workflow_file_path_to_info: dict[str, WorkflowInfo]

    # Track how many contexts we have that intend to squelch (set to False) altered_workflow_state event values.
    class WorkflowSquelchContext:
        """Context manager to squelch workflow altered events."""

        def __init__(self, manager: WorkflowManager):
            self.manager = manager

        def __enter__(self) -> None:
            self.manager._squelch_workflow_altered_count += 1

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
            self.manager._squelch_workflow_altered_count -= 1

    _squelch_workflow_altered_count: int = 0

    class WorkflowExecutionResult(NamedTuple):
        """Result of a workflow execution."""

        execution_successful: bool
        execution_details: str

    def __init__(self, event_manager: EventManager) -> None:
        self._workflow_file_path_to_info = {}
        self._squelch_workflow_altered_count = 0

        event_manager.assign_manager_to_request_type(
            RunWorkflowFromScratchRequest, self.on_run_workflow_from_scratch_request
        )
        event_manager.assign_manager_to_request_type(
            RunWorkflowWithCurrentStateRequest,
            self.on_run_workflow_with_current_state_request,
        )
        event_manager.assign_manager_to_request_type(
            RunWorkflowFromRegistryRequest,
            self.on_run_workflow_from_registry_request,
        )
        event_manager.assign_manager_to_request_type(
            RegisterWorkflowRequest,
            self.on_register_workflow_request,
        )
        event_manager.assign_manager_to_request_type(
            ListAllWorkflowsRequest,
            self.on_list_all_workflows_request,
        )
        event_manager.assign_manager_to_request_type(
            DeleteWorkflowRequest,
            self.on_delete_workflows_request,
        )
        event_manager.assign_manager_to_request_type(
            RenameWorkflowRequest,
            self.on_rename_workflow_request,
        )

        event_manager.assign_manager_to_request_type(
            SaveWorkflowRequest,
            self.on_save_workflow_request,
        )
        event_manager.assign_manager_to_request_type(LoadWorkflowMetadata, self.on_load_workflow_metadata_request)

    def print_workflow_load_status(self) -> None:
        workflow_file_paths = self.get_workflows_attempted_to_load()
        workflow_infos = []
        for workflow_file_path in workflow_file_paths:
            workflow_info = self.get_workflow_info_for_attempted_load(workflow_file_path)
            workflow_infos.append(workflow_info)

        console = Console()

        # Check if the list is empty
        if not workflow_infos:
            # Display a message indicating no workflows are available
            empty_message = Text("No workflow information available", style="italic")
            panel = Panel(empty_message, title="Workflow Information", border_style="blue")
            console.print(panel)
            return

        # Create a table with five columns and row dividers
        table = Table(show_header=True, box=HEAVY_EDGE, show_lines=True, expand=True)
        table.add_column("Workflow Name", style="green")
        table.add_column("Status", style="green")
        table.add_column("File Path", style="cyan")
        table.add_column("Problems", style="yellow")
        table.add_column("Dependencies", style="magenta")

        # Status emojis mapping
        status_emoji = {
            self.WorkflowStatus.GOOD: "✅",
            self.WorkflowStatus.FLAWED: "🟡",
            self.WorkflowStatus.UNUSABLE: "❌",
            self.WorkflowStatus.MISSING: "❓",
        }

        dependency_status_emoji = {
            self.WorkflowDependencyStatus.PERFECT: "✅",
            self.WorkflowDependencyStatus.GOOD: "👌",
            self.WorkflowDependencyStatus.CAUTION: "🟡",
            self.WorkflowDependencyStatus.BAD: "❌",
            self.WorkflowDependencyStatus.MISSING: "❓",
            self.WorkflowDependencyStatus.UNKNOWN: "❓",
        }

        # Add rows for each workflow info
        for wf_info in workflow_infos:
            # File path column
            file_path = wf_info.workflow_path
            file_path_text = Text(file_path, style="cyan")
            file_path_text.overflow = "fold"  # Force wrapping

            # Workflow name column with emoji based on status
            emoji = status_emoji.get(wf_info.status, "ERR: Unknown/Unexpected Workflow Status")
            name = wf_info.workflow_name if wf_info.workflow_name else "*UNKNOWN*"
            workflow_name = f"{emoji} {name}"

            # Problems column - format with numbers if there's more than one
            problems = "\n".join(wf_info.problems) if wf_info.problems else "No problems detected."

            # Dependencies column
            if wf_info.status == self.WorkflowStatus.MISSING or (
                wf_info.status == self.WorkflowStatus.UNUSABLE and not wf_info.workflow_dependencies
            ):
                dependencies = "❓ UNKNOWN"
            else:
                dependencies = (
                    "\n".join(
                        f"{dependency_status_emoji.get(dep.status, '?')} {dep.library_name} ({dep.version_requested}): {dep.status.value}"
                        for dep in wf_info.workflow_dependencies
                    )
                    if wf_info.workflow_dependencies
                    else "No dependencies"
                )

            table.add_row(
                workflow_name,
                wf_info.status.value,
                file_path_text,
                problems,
                dependencies,
            )

        # Wrap the table in a panel
        panel = Panel(table, title="Workflow Information", border_style="blue")
        console.print(panel)

    def get_workflows_attempted_to_load(self) -> list[str]:
        return list(self._workflow_file_path_to_info.keys())

    def get_workflow_info_for_attempted_load(self, workflow_file_path: str) -> WorkflowInfo:
        return self._workflow_file_path_to_info[workflow_file_path]

    def should_squelch_workflow_altered(self) -> bool:
        return self._squelch_workflow_altered_count > 0

    def run_workflow(self, relative_file_path: str) -> WorkflowExecutionResult:
        relative_file_path_obj = Path(relative_file_path)
        if relative_file_path_obj.is_absolute():
            complete_file_path = relative_file_path_obj
        else:
            complete_file_path = WorkflowRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        try:
            # TODO: scope the libraries loaded to JUST those used by this workflow, eventually: https://github.com/griptape-ai/griptape-nodes/issues/284
            # Load (or reload, which should trigger a hot reload) all libraries
            GriptapeNodes.LibraryManager().load_all_libraries_from_config()

            # Now execute the workflow.
            with Path(complete_file_path).open() as file:
                workflow_content = file.read()
            exec(workflow_content)  # noqa: S102
        except Exception as e:
            return WorkflowManager.WorkflowExecutionResult(
                execution_successful=False,
                execution_details=f"Failed to run workflow on path '{complete_file_path}'. Exception: {e}",
            )
        return WorkflowManager.WorkflowExecutionResult(
            execution_successful=True,
            execution_details=f"Succeeded in running workflow on path '{complete_file_path}'.",
        )

    def on_run_workflow_from_scratch_request(self, request: RunWorkflowFromScratchRequest) -> ResultPayload:
        # Squelch any ResultPayloads that indicate the workflow was changed, because we are loading it into a blank slate.
        with WorkflowManager.WorkflowSquelchContext(self):
            # Check if file path exists
            relative_file_path = request.file_path
            complete_file_path = WorkflowRegistry.get_complete_file_path(relative_file_path=relative_file_path)
            if not Path(complete_file_path).is_file():
                details = f"Failed to find file. Path '{complete_file_path}' doesn't exist."
                logger.error(details)
                return RunWorkflowFromScratchResultFailure()

            # Start with a clean slate.
            clear_all_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
            clear_all_result = GriptapeNodes.handle_request(clear_all_request)
            if not clear_all_result.succeeded():
                details = f"Failed to clear the existing object state when trying to run '{complete_file_path}'."
                logger.error(details)
                return RunWorkflowFromScratchResultFailure()

            # Run the file, goddamn it
            execution_result = self.run_workflow(relative_file_path=relative_file_path)
            if execution_result.execution_successful:
                logger.debug(execution_result.execution_details)
                return RunWorkflowFromScratchResultSuccess()

            logger.error(execution_result.execution_details)
            return RunWorkflowFromScratchResultFailure()

    def on_run_workflow_with_current_state_request(self, request: RunWorkflowWithCurrentStateRequest) -> ResultPayload:
        relative_file_path = request.file_path
        complete_file_path = WorkflowRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        if not Path(complete_file_path).is_file():
            details = f"Failed to find file. Path '{complete_file_path}' doesn't exist."
            logger.error(details)
            return RunWorkflowWithCurrentStateResultFailure()
        execution_result = self.run_workflow(relative_file_path=relative_file_path)

        if execution_result.execution_successful:
            logger.debug(execution_result.execution_details)
            return RunWorkflowWithCurrentStateResultSuccess()
        logger.error(execution_result.execution_details)
        return RunWorkflowWithCurrentStateResultFailure()

    def on_run_workflow_from_registry_request(self, request: RunWorkflowFromRegistryRequest) -> ResultPayload:
        # get workflow from registry
        try:
            workflow = WorkflowRegistry.get_workflow_by_name(request.workflow_name)
        except KeyError:
            logger.error("Failed to get workflow from registry.")
            return RunWorkflowFromRegistryResultFailure()

        # get file_path from workflow
        relative_file_path = workflow.file_path

        # Squelch any ResultPayloads that indicate the workflow was changed, because we are loading it.
        with WorkflowManager.WorkflowSquelchContext(self):
            if request.run_with_clean_slate:
                # Start with a clean slate.
                clear_all_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
                clear_all_result = GriptapeNodes.handle_request(clear_all_request)
                if not clear_all_result.succeeded():
                    details = f"Failed to clear the existing object state when preparing to run workflow '{request.workflow_name}'."
                    logger.error(details)
                    return RunWorkflowFromRegistryResultFailure()

                # Unload all libraries now.
                all_libraries_request = ListRegisteredLibrariesRequest()
                all_libraries_result = GriptapeNodes.handle_request(all_libraries_request)
                if not isinstance(all_libraries_result, ListRegisteredLibrariesResultSuccess):
                    details = f"When preparing to run a workflow '{request.workflow_name}', failed to get registered libraries."
                    logger.error(details)
                    return RunWorkflowFromRegistryResultFailure()

                for library_name in all_libraries_result.libraries:
                    unload_library_request = UnloadLibraryFromRegistryRequest(library_name=library_name)
                    unload_library_result = GriptapeNodes.handle_request(unload_library_request)
                    if not unload_library_result.succeeded():
                        details = f"When preparing to run a workflow '{request.workflow_name}', failed to unload library '{library_name}'."
                        logger.error(details)
                        return RunWorkflowFromRegistryResultFailure()

            # run file
            execution_result = self.run_workflow(relative_file_path=relative_file_path)

            if execution_result.execution_successful:
                logger.debug(execution_result.execution_details)
                return RunWorkflowFromRegistryResultSuccess()

            logger.error(execution_result.execution_details)
            return RunWorkflowFromRegistryResultFailure()

    def on_register_workflow_request(self, request: RegisterWorkflowRequest) -> ResultPayload:
        try:
            if isinstance(request.metadata, dict):
                request.metadata = WorkflowMetadata(**request.metadata)

            workflow = WorkflowRegistry.generate_new_workflow(metadata=request.metadata, file_path=request.file_name)
        except Exception as e:
            details = f"Failed to register workflow with name '{request.metadata.name}'. Error: {e}"
            logger.error(details)
            return RegisterWorkflowResultFailure()
        return RegisterWorkflowResultSuccess(workflow_name=workflow.metadata.name)

    def on_list_all_workflows_request(self, _request: ListAllWorkflowsRequest) -> ResultPayload:
        try:
            workflows = WorkflowRegistry.list_workflows()
        except Exception:
            details = "Failed to list all workflows."
            logger.error(details)
            return ListAllWorkflowsResultFailure()
        return ListAllWorkflowsResultSuccess(workflows=workflows)

    def on_delete_workflows_request(self, request: DeleteWorkflowRequest) -> ResultPayload:
        try:
            workflow = WorkflowRegistry.delete_workflow_by_name(request.name)
        except Exception as e:
            details = f"Failed to remove workflow from registry with name '{request.name}'. Exception: {e}"
            logger.error(details)
            return DeleteWorkflowResultFailure()
        config_manager = GriptapeNodes.ConfigManager()
        try:
            config_manager.delete_user_workflow(workflow.file_path)
        except Exception as e:
            details = f"Failed to remove workflow from user config with name '{request.name}'. Exception: {e}"
            logger.error(details)
            return DeleteWorkflowResultFailure()
        # delete the actual file
        full_path = config_manager.workspace_path.joinpath(workflow.file_path)
        try:
            full_path.unlink()
        except Exception as e:
            details = f"Failed to delete workflow file with path '{workflow.file_path}'. Exception: {e}"
            logger.error(details)
            return DeleteWorkflowResultFailure()
        return DeleteWorkflowResultSuccess()

    def on_rename_workflow_request(self, request: RenameWorkflowRequest) -> ResultPayload:
        save_workflow_request = GriptapeNodes.handle_request(SaveWorkflowRequest(file_name=request.requested_name))

        if isinstance(save_workflow_request, SaveWorkflowResultFailure):
            details = f"Attempted to rename workflow '{request.workflow_name}' to '{request.requested_name}'. Failed while attempting to save."
            logger.error(details)
            return RenameWorkflowResultFailure()

        delete_workflow_result = GriptapeNodes.handle_request(DeleteWorkflowRequest(name=request.workflow_name))
        if isinstance(delete_workflow_result, DeleteWorkflowResultFailure):
            details = f"Attempted to rename workflow '{request.workflow_name}' to '{request.requested_name}'. Failed while attempting to remove the original file name from the registry."
            logger.error(details)
            return RenameWorkflowResultFailure()

        return RenameWorkflowResultSuccess()

    def on_load_workflow_metadata_request(  # noqa: C901, PLR0912, PLR0915
        self, request: LoadWorkflowMetadata
    ) -> ResultPayload:
        # Let us go into the darkness.
        complete_file_path = GriptapeNodes.ConfigManager().workspace_path.joinpath(request.file_name)
        str_path = str(complete_file_path)
        if not Path(complete_file_path).is_file():
            self._workflow_file_path_to_info[str(str_path)] = WorkflowManager.WorkflowInfo(
                status=WorkflowManager.WorkflowStatus.MISSING,
                workflow_path=str_path,
                workflow_name=None,
                workflow_dependencies=[],
                problems=["Workflow could not be found at the path specified."],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}. Failed because no file could be found at that path."
            logger.error(details)
            return LoadWorkflowMetadataResultFailure()

        # Open 'er up.
        with complete_file_path.open("r") as file:
            workflow_content = file.read()

        # Find the metadata block.
        regex = r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"
        block_name = "script"
        matches = list(
            filter(
                lambda m: m.group("type") == block_name,
                re.finditer(regex, workflow_content),
            )
        )
        if len(matches) != 1:
            self._workflow_file_path_to_info[str(str_path)] = WorkflowManager.WorkflowInfo(
                status=WorkflowManager.WorkflowStatus.UNUSABLE,
                workflow_path=str_path,
                workflow_name=None,
                workflow_dependencies=[],
                problems=[
                    f"Failed as it had {len(matches)} sections titled '{block_name}', and we expect exactly 1 such section."
                ],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed as it had {len(matches)} sections titled '{block_name}', and we expect exactly 1 such section."
            logger.error(details)
            return LoadWorkflowMetadataResultFailure()

        # Now attempt to parse out the metadata section, stripped of comment prefixes.
        metadata_content_toml = "".join(
            line[2:] if line.startswith("# ") else line[1:]
            for line in matches[0].group("content").splitlines(keepends=True)
        )

        try:
            toml_doc = tomlkit.parse(metadata_content_toml)
        except Exception as err:
            self._workflow_file_path_to_info[str(str_path)] = WorkflowManager.WorkflowInfo(
                status=WorkflowManager.WorkflowStatus.UNUSABLE,
                workflow_path=str_path,
                workflow_name=None,
                workflow_dependencies=[],
                problems=[f"Failed because the metadata was not valid TOML: {err}"],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed because the metadata was not valid TOML: {err}"
            logger.error(details)
            return LoadWorkflowMetadataResultFailure()

        tool_header = "tool"
        griptape_nodes_header = "griptape-nodes"
        try:
            griptape_nodes_tool_section = toml_doc[tool_header][griptape_nodes_header]  # type: ignore (this is the only way I could find to get tomlkit to do the dotted notation correctly)
        except Exception as err:
            self._workflow_file_path_to_info[str(str_path)] = WorkflowManager.WorkflowInfo(
                status=WorkflowManager.WorkflowStatus.UNUSABLE,
                workflow_path=str_path,
                workflow_name=None,
                workflow_dependencies=[],
                problems=[f"Failed because the '[{tool_header}.{griptape_nodes_header}]' section could not be found."],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed because the '[{tool_header}.{griptape_nodes_header}]' section could not be found: {err}"
            logger.error(details)
            return LoadWorkflowMetadataResultFailure()

        try:
            # Is it kosher?
            workflow_metadata = WorkflowMetadata.model_validate(griptape_nodes_tool_section)
        except Exception as err:
            # No, it is haram.
            self._workflow_file_path_to_info[str(str_path)] = WorkflowManager.WorkflowInfo(
                status=WorkflowManager.WorkflowStatus.UNUSABLE,
                workflow_path=str_path,
                workflow_name=None,
                workflow_dependencies=[],
                problems=[
                    f"Failed because the metadata in the '[{tool_header}.{griptape_nodes_header}]' section did not match the requisite schema with error: {err}"
                ],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed because the metadata in the '[{tool_header}.{griptape_nodes_header}]' section did not match the requisite schema with error: {err}"
            logger.error(details)
            return LoadWorkflowMetadataResultFailure()

        # We have valid dependencies, etc.
        # TODO: validate schema versions, engine versions: https://github.com/griptape-ai/griptape-nodes/issues/617
        problems = []
        had_critical_error = False

        # Confirm dates are correct.
        if workflow_metadata.creation_date is None:
            # Assign it to the epoch start and flag it as a warning.
            workflow_metadata.creation_date = WorkflowManager.EPOCH_START
            problems.append(
                f"Workflow metadata was missing a creation date. Defaulting to {WorkflowManager.EPOCH_START}. This value will be replaced with the current date the first time it is saved."
            )
        if workflow_metadata.last_modified_date is None:
            # Assign it to the epoch start and flag it as a warning.
            workflow_metadata.last_modified_date = WorkflowManager.EPOCH_START
            problems.append(
                f"Workflow metadata was missing a last modified date. Defaulting to {WorkflowManager.EPOCH_START}. This value will be replaced with the current date the first time it is saved."
            )

        dependency_infos = []
        for node_library_referenced in workflow_metadata.node_libraries_referenced:
            library_name = node_library_referenced.library_name
            desired_version_str = node_library_referenced.library_version
            desired_version = Version.from_string(desired_version_str)
            if desired_version is None:
                had_critical_error = True
                problems.append(
                    f"Workflow cited an invalid version string '{desired_version_str}' for library '{library_name}'. Must be specified in major.minor.patch format."
                )
                dependency_infos.append(
                    WorkflowManager.WorkflowDependencyInfo(
                        library_name=library_name,
                        version_requested=desired_version_str,
                        version_present=None,
                        status=WorkflowManager.WorkflowDependencyStatus.UNKNOWN,
                    )
                )
                # SKIP IT.
                continue
            # See how our desired version compares against the actual library we (may) have.
            # See if the library exists.
            library_metadata_request = GetLibraryMetadataRequest(library=library_name)
            library_metadata_result = GriptapeNodes.handle_request(library_metadata_request)
            if not isinstance(library_metadata_result, GetLibraryMetadataResultSuccess):
                # Metadata failed to be found.
                had_critical_error = True
                problems.append(
                    f"Library '{library_name}' was not successfully registered. It may have other problems that prevented it from loading."
                )
                dependency_infos.append(
                    WorkflowManager.WorkflowDependencyInfo(
                        library_name=library_name,
                        version_requested=desired_version_str,
                        version_present=None,
                        status=WorkflowManager.WorkflowDependencyStatus.MISSING,
                    )
                )
                # SKIP IT.
                continue

            # Is there a version string in the metadata?
            library_metadata = library_metadata_result.metadata
            version_key = "library_version"
            if version_key not in library_metadata:
                had_critical_error = True
                problems.append(
                    f"Library '{library_name}' has malformed metadata. Was unable to find required field '{version_key}'."
                )
                dependency_infos.append(
                    WorkflowManager.WorkflowDependencyInfo(
                        library_name=library_name,
                        version_requested=desired_version_str,
                        version_present=None,
                        status=WorkflowManager.WorkflowDependencyStatus.MISSING,
                    )
                )
                # SKIP IT.
                continue

            # Attempt to parse out the version string.
            library_version_str = library_metadata[version_key]
            library_version = Version.from_string(version_string=library_version_str)
            if library_version is None:
                had_critical_error = True
                problems.append(
                    f"Library an invalid version string '{library_version_str}' for library '{library_name}'. Must be specified in major.minor.patch format."
                )
                dependency_infos.append(
                    WorkflowManager.WorkflowDependencyInfo(
                        library_name=library_name,
                        version_requested=desired_version_str,
                        version_present=None,
                        status=WorkflowManager.WorkflowDependencyStatus.UNKNOWN,
                    )
                )
                # SKIP IT.
                continue
            # How does it compare?
            major_matches = library_version.major == desired_version.major
            minor_matches = library_version.minor == desired_version.minor
            patch_matches = library_version.patch == desired_version.patch
            if major_matches and minor_matches and patch_matches:
                status = WorkflowManager.WorkflowDependencyStatus.PERFECT
            elif major_matches and minor_matches:
                status = WorkflowManager.WorkflowDependencyStatus.GOOD
            elif major_matches:
                # Let's see if the dependency is ahead and within our tolerance.
                delta = library_version.minor - desired_version.minor
                if delta < 0:
                    problems.append(
                        f"Library '{library_name}' is at version '{library_version}', which is below the desired version."
                    )
                    status = WorkflowManager.WorkflowDependencyStatus.BAD
                    had_critical_error = True
                elif delta > WorkflowManager.MAX_MINOR_VERSION_DEVIATION:
                    problems.append(
                        f"Library '{library_name}' is at version '{library_version}', but this workflow requested '{desired_version}'. This version difference is too far out of tolerance to recommend proceeding."
                    )
                    status = WorkflowManager.WorkflowDependencyStatus.BAD
                    had_critical_error = True
                else:
                    problems.append(
                        f"Library '{library_name}' is at version '{library_version}', but this workflow requested '{desired_version}'. There may be incompatibilities. Proceed at your own risk."
                    )
                    status = WorkflowManager.WorkflowDependencyStatus.CAUTION
            else:
                problems.append(
                    f"Library '{library_name}' is at version '{library_version}', but this workflow requested '{desired_version}'. Major version differences have breaking changes that this Workflow may not support."
                )
                status = WorkflowManager.WorkflowDependencyStatus.BAD
                had_critical_error = True

            # Append the latest info for this dependency.
            dependency_infos.append(
                WorkflowManager.WorkflowDependencyInfo(
                    library_name=library_name,
                    version_requested=str(desired_version),
                    version_present=str(library_version),
                    status=status,
                )
            )
        # OK, we have all of our dependencies together. Let's look at the overall scenario.
        if had_critical_error:
            overall_status = WorkflowManager.WorkflowStatus.UNUSABLE
        elif problems:
            overall_status = WorkflowManager.WorkflowStatus.FLAWED
        else:
            overall_status = WorkflowManager.WorkflowStatus.GOOD

        self._workflow_file_path_to_info[str(str_path)] = WorkflowManager.WorkflowInfo(
            status=overall_status,
            workflow_path=str_path,
            workflow_name=workflow_metadata.name,
            workflow_dependencies=dependency_infos,
            problems=problems,
        )
        return LoadWorkflowMetadataResultSuccess(metadata=workflow_metadata)

    def _gather_workflow_imports(self) -> list[str]:
        """Gathers all the imports for the saved workflow file, specifically for the events."""
        import_template = "from {} import *"
        import_statements = []

        from griptape_nodes.retained_mode import events as events_pkg

        # Iterate over all modules in the events package
        for _finder, module_name, _is_pkg in pkgutil.iter_modules(events_pkg.__path__, events_pkg.__name__ + "."):
            if module_name.endswith("generate_request_payload_schemas"):
                continue
            import_statements.append(import_template.format(module_name))

        return import_statements

    def on_save_workflow_request(  # noqa: C901, PLR0911, PLR0912, PLR0915
        self, request: SaveWorkflowRequest
    ) -> ResultPayload:
        obj_manager = GriptapeNodes.ObjectManager()
        node_manager = GriptapeNodes.NodeManager()
        config_manager = GriptapeNodes.ConfigManager()

        local_tz = datetime.now().astimezone().tzinfo

        # Start with the file name provided; we may change it.
        file_name = request.file_name

        # See if we had an existing workflow for this.
        prior_workflow = None
        creation_date = None
        if file_name and WorkflowRegistry.has_workflow_with_name(file_name):
            # Get the metadata.
            prior_workflow = WorkflowRegistry.get_workflow_by_name(file_name)
            # We'll use it's creation date.
            creation_date = prior_workflow.metadata.creation_date

        if (creation_date is None) or (creation_date == WorkflowManager.EPOCH_START):
            # Either a new workflow, or a backcompat situation.
            creation_date = datetime.now(tz=local_tz)

        # Let's see if this is a template file; if so, re-route it as a copy in the customer's workflow directory.
        if prior_workflow and prior_workflow.metadata.is_template:
            # Aha! User is attempting to save a template. Create a differently-named file in their workspace.
            # Find the first available file name that doesn't conflict.
            curr_idx = 1
            free_file_found = False
            while not free_file_found:
                # Composite a new candidate file name to test.
                new_file_name = f"{file_name}_{curr_idx}"
                new_file_name_with_extension = f"{new_file_name}.py"
                new_file_full_path = config_manager.workspace_path.joinpath(new_file_name_with_extension)
                if new_file_full_path.exists():
                    # Keep going.
                    curr_idx += 1
                else:
                    free_file_found = True
                    file_name = new_file_name

        # open my file
        if not file_name:
            file_name = datetime.now(tz=local_tz).strftime("%d.%m_%H.%M")
        relative_file_path = f"{file_name}.py"
        file_path = config_manager.workspace_path.joinpath(relative_file_path)
        created_flows = []
        node_libraries_used = set()

        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Get the engine version.
        engine_version_request = GetEngineVersionRequest()
        engine_version_result = GriptapeNodes.handle_request(request=engine_version_request)
        if not engine_version_result.succeeded():
            details = f"Attempted to save workflow '{relative_file_path}', but failed getting the engine version."
            logger.error(details)
            return SaveWorkflowResultFailure()
        try:
            engine_version_success = cast("GetEngineVersionResultSuccess", engine_version_result)
            engine_version = (
                f"{engine_version_success.major}.{engine_version_success.minor}.{engine_version_success.patch}"
            )
        except Exception as err:
            details = f"Attempted to save workflow '{relative_file_path}', but failed getting the engine version: {err}"
            logger.error(details)
            return SaveWorkflowResultFailure()

        try:
            with file_path.open("w") as file:
                # Now the critical import.
                file.write("from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes\n")
                # Now the event imports.
                for import_statement in self._gather_workflow_imports():
                    file.write(import_statement + "\n")
                # Write all flows to a file, get back the strings for connections
                connection_request_workflows = handle_flow_saving(file, obj_manager, created_flows)
                # Now all of the flows have been created.
                values_created = {}
                for node in obj_manager.get_filtered_subset(type=BaseNode).values():
                    flow_name = node_manager.get_node_parent_flow_by_name(node.name)
                    # Save the parameters
                    try:
                        parameter_string, saved_properly = handle_parameter_creation_saving(node, values_created)
                    except Exception as e:
                        details = f"Failed to save workflow because failed to save parameter creation for node '{node.name}'. Error: {e}"
                        logger.error(details)
                        return SaveWorkflowResultFailure()
                    if saved_properly:
                        resolution = node.state.value
                    else:
                        resolution = NodeResolutionState.UNRESOLVED.value
                    creation_request = CreateNodeRequest(
                        node_type=node.__class__.__name__,
                        node_name=node.name,
                        metadata=node.metadata,
                        override_parent_flow_name=flow_name,
                        resolution=resolution,  # Unresolved if something failed to save or create
                        initial_setup=True,
                    )
                    code_string = f"GriptapeNodes.handle_request({creation_request})"
                    file.write(code_string + "\n")
                    # Add all parameter deetails now
                    file.write(parameter_string)

                    # See if this node uses a library we need to know about.
                    library_used = node.metadata["library"]
                    # Get the library metadata so we can get the version.
                    library_metadata_request = GetLibraryMetadataRequest(library=library_used)
                    library_metadata_result = GriptapeNodes.LibraryManager().get_library_metadata_request(
                        library_metadata_request
                    )
                    if not library_metadata_result.succeeded():
                        details = f"Attempted to save workflow '{relative_file_path}', but failed to get library metadata for library '{library_used}'."
                        logger.error(details)
                        return SaveWorkflowResultFailure()
                    try:
                        library_metadata_success = cast("GetLibraryMetadataResultSuccess", library_metadata_result)
                        library_version = library_metadata_success.metadata["library_version"]
                    except Exception as err:
                        details = f"Attempted to save workflow '{relative_file_path}', but failed to get library version from metadata for library '{library_used}': {err}."
                        logger.error(details)
                        return SaveWorkflowResultFailure()
                    library_and_version = LibraryNameAndVersion(
                        library_name=library_used, library_version=library_version
                    )
                    node_libraries_used.add(library_and_version)
                # Now all nodes AND parameters have been created
                file.write(connection_request_workflows)

                # Now that we have the info about what's actually being used, save out the workflow metadata.
                workflow_metadata = WorkflowMetadata(
                    name=str(file_name),
                    schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
                    engine_version_created_with=engine_version,
                    node_libraries_referenced=list(node_libraries_used),
                    creation_date=creation_date,
                    last_modified_date=datetime.now(tz=local_tz),
                )

                try:
                    toml_doc = tomlkit.document()
                    toml_doc.add("dependencies", tomlkit.item([]))
                    griptape_tool_table = tomlkit.table()
                    metadata_dict = workflow_metadata.model_dump()
                    for key, value in metadata_dict.items():
                        # Strip out the Nones since TOML doesn't like those.
                        if value is not None:
                            griptape_tool_table.add(key=key, value=value)
                    toml_doc["tool"] = tomlkit.table()
                    toml_doc["tool"]["griptape-nodes"] = griptape_tool_table  # type: ignore (this is the only way I could find to get tomlkit to do the dotted notation correctly)
                except Exception as err:
                    details = f"Attempted to save workflow '{relative_file_path}', but failed to get metadata into TOML format: {err}."
                    logger.error(details)
                    return SaveWorkflowResultFailure()

                # Format the metadata block with comment markers for each line
                toml_lines = tomlkit.dumps(toml_doc).split("\n")
                commented_toml_lines = ["# " + line for line in toml_lines]

                # Create the complete metadata block
                header = f"# /// {WorkflowManager.WORKFLOW_METADATA_HEADER}"
                metadata_lines = [header]
                metadata_lines.extend(commented_toml_lines)
                metadata_lines.append("# ///")
                metadata_lines.append("\n\n")
                metadata_block = "\n".join(metadata_lines)

                file.write(metadata_block)
        except Exception as e:
            details = f"Failed to save workflow, exception: {e}"
            logger.error(details)
            return SaveWorkflowResultFailure()

        # save the created workflow to a personal json file
        registered_workflows = WorkflowRegistry.list_workflows()
        if file_name not in registered_workflows:
            config_manager.save_user_workflow_json(str(file_path))
            WorkflowRegistry.generate_new_workflow(metadata=workflow_metadata, file_path=relative_file_path)
        details = f"Successfully saved workflow to: {file_path}"
        logger.info(details)

        # Now let's try all this with the serialized flow.
        top_level_flow_request = GetTopLevelFlowRequest()
        top_level_flow_result = GriptapeNodes.handle_request(top_level_flow_request)
        if not isinstance(top_level_flow_result, GetTopLevelFlowResultSuccess):
            details = (
                f"Attempted to save workflow '{relative_file_path}'. Failed when requesting to get top level flow."
            )
            logger.error(details)
            return SaveWorkflowResultFailure()
        top_level_flow_name = top_level_flow_result.flow_name
        serialized_flow_request = SerializeFlowToCommandsRequest(
            flow_name=top_level_flow_name, include_create_flow_command=True
        )
        serialized_flow_result = GriptapeNodes.handle_request(serialized_flow_request)
        if not isinstance(serialized_flow_result, SerializeFlowToCommandsResultSuccess):
            details = f"Attempted to save workflow '{relative_file_path}'. Failed when serializing flow."
            logger.error(details)
            return SaveWorkflowResultFailure()
        serialized_flow_commands = serialized_flow_result.serialized_flow_commands

        import_recorder = WorkflowManager.ImportRecorder()
        import_recorder.add_from_import("griptape_nodes.retained_mode.griptape_nodes", "GriptapeNodes")
        import_recorder.add_from_import("griptape_nodes.retained_mode.managers.context_manager", "ContextManager")

        ast_container = WorkflowManager.ASTContainer()

        # Generate unique values code AST node
        unique_values_node = WorkflowManager._generate_unique_values_code(
            unique_parameter_values=serialized_flow_commands.unique_parameter_values,
            prefix="top_level",
            import_recorder=import_recorder,
        )
        ast_container.add_node(unique_values_node)

        # Extract create_flow_command from serialized_flow_commands
        create_flow_command = serialized_flow_commands.create_flow_command

        if create_flow_command is not None:
            # Generate create flow context AST node
            create_flow_context_node = WorkflowManager._generate_create_flow(create_flow_command, import_recorder)
            ast_container.add_node(create_flow_context_node)

        # Generate assign flow context AST node
        assign_flow_context_node = WorkflowManager._generate_assign_flow_context(create_flow_command, import_recorder)

        # Generate nodes in flow AST node
        nodes_in_flow = WorkflowManager._generate_nodes_in_flow(serialized_flow_commands, import_recorder)

        # Add the nodes to the body of the with statement
        assign_flow_context_node.body.extend(nodes_in_flow)
        ast_container.add_node(assign_flow_context_node)

        # Generate final code from ASTContainer
        ast_output = "\n\n".join([ast.unparse(node) for node in ast_container.get_ast()])
        import_output = import_recorder.generate_imports()
        final_code_output = f"{import_output}\n\n{ast_output}"

        relative_serialized_file_path = f"{file_name}_serialize_test.py"
        serialized_file_path = config_manager.workspace_path.joinpath(relative_serialized_file_path)
        with serialized_file_path.open("w") as file:
            file.write(final_code_output)

        return SaveWorkflowResultSuccess(file_path=str(file_path))

    class ASTContainer:
        """ASTContainer is a helper class to keep track of AST nodes and generate final code from them."""

        def __init__(self) -> None:
            """Initialize an empty list to store AST nodes."""
            self.nodes = []

        def add_node(self, node: ast.AST) -> None:
            self.nodes.append(node)

        def get_ast(self) -> list[ast.AST]:
            return self.nodes

    @dataclass
    class ImportRecorder:
        """Recorder to keep track of imports and generate code for them."""

        imports: set[str]
        from_imports: dict[str, set[str]]

        def __init__(self) -> None:
            """Initialize the recorder."""
            self.imports = set()
            self.from_imports = {}

        def add_import(self, module_name: str) -> None:
            """Add an import to the recorder.

            Args:
                module_name (str): The module name to import.
            """
            self.imports.add(module_name)

        def add_from_import(self, module_name: str, class_name: str) -> None:
            """Add a from-import to the recorder.

            Args:
                module_name (str): The module name to import from.
                class_name (str): The class name to import.
            """
            if module_name not in self.from_imports:
                self.from_imports[module_name] = set()
            self.from_imports[module_name].add(class_name)

        def generate_imports(self) -> str:
            """Generate the import code from the recorded imports.

            Returns:
                str: The generated code.
            """
            import_lines = []
            for module_name in sorted(self.imports):
                import_lines.append(f"import {module_name}")  # noqa: PERF401

            for module_name, class_names in sorted(self.from_imports.items()):
                sorted_class_names = sorted(class_names)
                import_lines.append(f"from {module_name} import {', '.join(sorted_class_names)}")

            return "\n".join(import_lines)

    @staticmethod
    def _generate_unique_values_code(
        unique_parameter_values: list[Any], prefix: str, import_recorder: ImportRecorder
    ) -> ast.AST:
        import_recorder.add_import("pickle")

        # Serialize the unique values as pickled strings.
        unique_parameter_byte_strs = []
        for unique_parameter_value in unique_parameter_values:
            unique_parameter_bytes = pickle.dumps(unique_parameter_value)
            # Encode the bytes as a string using latin1
            unique_parameter_byte_str = unique_parameter_bytes.decode("latin1")
            unique_parameter_byte_strs.append(unique_parameter_byte_str)

        # Generate a comment explaining what we're doing:
        comment_text = (
            "\n"
            "1. We've collated all of the unique parameter values into a list so that we do not have to duplicate them.\n"
            "   This minimizes the size of the code, especially for large objects like serialized image files.\n"
            "2. We're using a prefix so that it's clear which Flow these values are associated with.\n"
            "3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes\n"
            "   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise\n"
            "   would be difficult to serialize.\n"
        )

        # Generate the list of unique values
        unique_values_list_name = f"{prefix}_unique_values_list"
        unique_values_ast = ast.Assign(
            targets=[ast.Name(id=unique_values_list_name, ctx=ast.Store(), lineno=1, col_offset=0)],
            value=ast.List(
                elts=[
                    ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="pickle", ctx=ast.Load(), lineno=1, col_offset=0),
                            attr="loads",
                            ctx=ast.Load(),
                            lineno=1,
                            col_offset=0,
                        ),
                        args=[ast.Constant(value=byte_str.encode("latin1"), lineno=1, col_offset=0)],
                        keywords=[],
                        lineno=1,
                        col_offset=0,
                    )
                    for byte_str in unique_parameter_byte_strs
                ],
                ctx=ast.Load(),
                lineno=1,
                col_offset=0,
            ),
            lineno=1,
            col_offset=0,
        )

        # Create the final AST with comments
        module_body = [
            ast.Expr(value=ast.Constant(value=comment_text, lineno=1, col_offset=0), lineno=1, col_offset=0),
            unique_values_ast,
        ]
        full_ast = ast.Module(body=module_body, type_ignores=[])
        return full_ast

    @staticmethod
    def _generate_create_flow(create_flow_command: CreateFlowRequest, import_recorder: ImportRecorder) -> ast.AST:
        import_recorder.add_from_import("griptape_nodes.retained_mode.events.flow_events", "CreateFlowRequest")

        # Prepare arguments for CreateFlowRequest
        create_flow_request_args = []

        # Omit values that match default values.
        if is_dataclass(create_flow_command):
            for field in fields(create_flow_command):
                field_value = getattr(create_flow_command, field.name)
                if field_value != field.default:
                    create_flow_request_args.append(
                        ast.keyword(arg=field.name, value=ast.Constant(value=field_value, lineno=1, col_offset=0))
                    )

        # Construct the AST for creating the flow
        create_flow_result = ast.Assign(
            targets=[ast.Name(id="create_flow_result", ctx=ast.Store(), lineno=1, col_offset=0)],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="GriptapeNodes", ctx=ast.Load(), lineno=1, col_offset=0),
                    attr="handle_request",
                    ctx=ast.Load(),
                    lineno=1,
                    col_offset=0,
                ),
                args=[
                    ast.Call(
                        func=ast.Name(id="CreateFlowRequest", ctx=ast.Load(), lineno=1, col_offset=0),
                        args=[],
                        keywords=create_flow_request_args,
                        lineno=1,
                        col_offset=0,
                    )
                ],
                keywords=[],
                lineno=1,
                col_offset=0,
            ),
            lineno=1,
            col_offset=0,
        )

        return create_flow_result

    @staticmethod
    def _generate_assign_flow_context(
        create_flow_command: CreateFlowRequest | None, import_recorder: ImportRecorder
    ) -> ast.With:
        context_manager = ast.Attribute(
            value=ast.Name(id="GriptapeNodes", ctx=ast.Load(), lineno=1, col_offset=0),
            attr="ContextManager",
            ctx=ast.Load(),
            lineno=1,
            col_offset=0,
        )

        if create_flow_command is None:
            # Construct AST for "GriptapeNodes.ContextManager().flow(GriptapeNodes.ContextManager().get_current_flow_name())"
            flow_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Call(func=context_manager, args=[], keywords=[], lineno=1, col_offset=0),
                    attr="flow",
                    ctx=ast.Load(),
                    lineno=1,
                    col_offset=0,
                ),
                args=[
                    ast.Call(
                        func=ast.Attribute(
                            value=ast.Call(func=context_manager, args=[], keywords=[], lineno=1, col_offset=0),
                            attr="get_current_flow_name",
                            ctx=ast.Load(),
                            lineno=1,
                            col_offset=0,
                        ),
                        args=[],
                        keywords=[],
                        lineno=1,
                        col_offset=0,
                    )
                ],
                keywords=[],
                lineno=1,
                col_offset=0,
            )
        else:
            # Construct AST for "GriptapeNodes.ContextManager().flow(create_flow_result.flow_name)"
            flow_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Call(func=context_manager, args=[], keywords=[], lineno=1, col_offset=0),
                    attr="flow",
                    ctx=ast.Load(),
                    lineno=1,
                    col_offset=0,
                ),
                args=[
                    ast.Attribute(
                        value=ast.Name(id="create_flow_result", ctx=ast.Load(), lineno=1, col_offset=0),
                        attr="flow_name",
                        ctx=ast.Load(),
                        lineno=1,
                        col_offset=0,
                    )
                ],
                keywords=[],
                lineno=1,
                col_offset=0,
            )

        # Construct the "with" statement with an empty body
        with_stmt = ast.With(
            items=[ast.withitem(context_expr=flow_call, optional_vars=None)],
            body=[],  # Initialize the body as an empty list
            type_comment=None,
            lineno=1,
            col_offset=0,
        )

        return with_stmt

    @staticmethod
    def _generate_nodes_in_flow(
        serialized_flow_commands: SerializedFlowCommands, import_recorder: ImportRecorder
    ) -> list[ast.stmt]:
        # Generate node creation code and add it to the flow context
        node_creation_asts = []
        for node_index, serialized_node_command in enumerate(serialized_flow_commands.serialized_node_commands):
            node_creation_ast = WorkflowManager._generate_node_creation_code(
                serialized_node_command, node_index, import_recorder
            )
            node_creation_asts.extend(node_creation_ast)
        return node_creation_asts

    @staticmethod
    def _generate_node_creation_code(
        serialized_node_command: SerializedNodeCommands, node_index: int, import_recorder: ImportRecorder
    ) -> list[ast.stmt]:
        # Ensure necessary imports are recorded
        import_recorder.add_from_import("griptape_nodes.retained_mode.events.node_events", "CreateNodeRequest")
        import_recorder.add_from_import("griptape_nodes.retained_mode.events.node_events", "CreateNodeResultSuccess")

        # Construct AST for the function body
        node_creation_ast = []

        # Create the CreateNodeRequest parameters
        create_node_request = serialized_node_command.create_node_command
        create_node_request_args = []

        if is_dataclass(create_node_request):
            for field in fields(create_node_request):
                field_value = getattr(create_node_request, field.name)
                if field_value != field.default:
                    create_node_request_args.append(
                        ast.keyword(arg=field.name, value=ast.Constant(value=field_value, lineno=1, col_offset=0))
                    )

        # Handle the create node command and assign to node name
        create_node_call_ast = ast.Assign(
            targets=[ast.Name(id=f"node{node_index}_name", ctx=ast.Store(), lineno=1, col_offset=0)],
            value=ast.Attribute(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="GriptapeNodes", ctx=ast.Load(), lineno=1, col_offset=0),
                        attr="handle_request",
                        ctx=ast.Load(),
                        lineno=1,
                        col_offset=0,
                    ),
                    args=[
                        ast.Call(
                            func=ast.Name(id="CreateNodeRequest", ctx=ast.Load(), lineno=1, col_offset=0),
                            args=[],
                            keywords=create_node_request_args,
                            lineno=1,
                            col_offset=0,
                        )
                    ],
                    keywords=[],
                    lineno=1,
                    col_offset=0,
                ),
                attr="node_name",
                ctx=ast.Load(),
                lineno=1,
                col_offset=0,
            ),
            lineno=1,
            col_offset=0,
        )

        node_creation_ast.append(create_node_call_ast)

        # Only add the 'with' statement if there are element_modification_commands
        if serialized_node_command.element_modification_commands:
            # Create the 'with' statement for the node context
            with_stmt = ast.With(
                items=[
                    ast.withitem(
                        context_expr=ast.Call(
                            func=ast.Attribute(
                                value=ast.Call(
                                    func=ast.Attribute(
                                        value=ast.Name(id="GriptapeNodes", ctx=ast.Load(), lineno=1, col_offset=0),
                                        attr="ContextManager",
                                        ctx=ast.Load(),
                                        lineno=1,
                                        col_offset=0,
                                    ),
                                    args=[],
                                    keywords=[],
                                    lineno=1,
                                    col_offset=0,
                                ),
                                attr="node",
                                ctx=ast.Load(),
                                lineno=1,
                                col_offset=0,
                            ),
                            args=[ast.Name(id=f"node{node_index}_name", ctx=ast.Load(), lineno=1, col_offset=0)],
                            keywords=[],
                            lineno=1,
                            col_offset=0,
                        ),
                        optional_vars=None,
                    )
                ],
                body=[],
                type_comment=None,
                lineno=1,
                col_offset=0,
            )

            # Generate handle_request calls for element_modification_commands
            for element_command in serialized_node_command.element_modification_commands:
                # Strip default values from element_command
                element_command_args = []
                if is_dataclass(element_command):
                    for field in fields(element_command):
                        field_value = getattr(element_command, field.name)
                        if field_value != field.default:
                            element_command_args.append(
                                ast.keyword(
                                    arg=field.name, value=ast.Constant(value=field_value, lineno=1, col_offset=0)
                                )
                            )

                # Create the handle_request call
                handle_request_call = ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="GriptapeNodes", ctx=ast.Load(), lineno=1, col_offset=0),
                            attr="handle_request",
                            ctx=ast.Load(),
                            lineno=1,
                            col_offset=0,
                        ),
                        args=[
                            ast.Call(
                                func=ast.Name(
                                    id=element_command.__class__.__name__, ctx=ast.Load(), lineno=1, col_offset=0
                                ),
                                args=[],
                                keywords=element_command_args,
                                lineno=1,
                                col_offset=0,
                            )
                        ],
                        keywords=[],
                        lineno=1,
                        col_offset=0,
                    ),
                    lineno=1,
                    col_offset=0,
                )
                with_stmt.body.append(handle_request_call)

            node_creation_ast.append(with_stmt)

        return node_creation_ast
