from __future__ import annotations

import ast
import asyncio
import logging
import pickle
import re
from collections import defaultdict
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from inspect import getmodule, isclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, TypeVar, cast

import aiofiles
import semver
import tomlkit
from rich.box import HEAVY_EDGE
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, EndNode, StartNode
from griptape_nodes.node_library.workflow_registry import (
    Workflow,
    WorkflowMetadata,
    WorkflowRegistry,
    WorkflowShape,
)
from griptape_nodes.retained_mode.events.app_events import (
    EngineInitializationProgress,
    GetEngineVersionRequest,
    GetEngineVersionResultSuccess,
    InitializationPhase,
    InitializationStatus,
)

# Runtime imports for ResultDetails since it's used at runtime
from griptape_nodes.retained_mode.events.base_events import AppEvent, ResultDetail, ResultDetails
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
    SerializedFlowCommands,
    SerializeFlowToCommandsRequest,
    SerializeFlowToCommandsResultSuccess,
    SetFlowMetadataRequest,
    SetFlowMetadataResultSuccess,
)
from griptape_nodes.retained_mode.events.library_events import (
    GetLibraryMetadataRequest,
    GetLibraryMetadataResultSuccess,
    ListRegisteredLibrariesRequest,
    ListRegisteredLibrariesResultSuccess,
)
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.events.workflow_events import (
    BranchWorkflowRequest,
    BranchWorkflowResultFailure,
    BranchWorkflowResultSuccess,
    CompareWorkflowsRequest,
    CompareWorkflowsResultFailure,
    CompareWorkflowsResultSuccess,
    DeleteWorkflowRequest,
    DeleteWorkflowResultFailure,
    DeleteWorkflowResultSuccess,
    ImportWorkflowAsReferencedSubFlowRequest,
    ImportWorkflowAsReferencedSubFlowResultFailure,
    ImportWorkflowAsReferencedSubFlowResultSuccess,
    ImportWorkflowRequest,
    ImportWorkflowResultFailure,
    ImportWorkflowResultSuccess,
    ListAllWorkflowsRequest,
    ListAllWorkflowsResultFailure,
    ListAllWorkflowsResultSuccess,
    LoadWorkflowMetadata,
    LoadWorkflowMetadataResultFailure,
    LoadWorkflowMetadataResultSuccess,
    MergeWorkflowBranchRequest,
    MergeWorkflowBranchResultFailure,
    MergeWorkflowBranchResultSuccess,
    MoveWorkflowRequest,
    MoveWorkflowResultFailure,
    MoveWorkflowResultSuccess,
    PublishWorkflowRequest,
    PublishWorkflowResultFailure,
    PublishWorkflowResultSuccess,
    RegisterWorkflowRequest,
    RegisterWorkflowResultFailure,
    RegisterWorkflowResultSuccess,
    RegisterWorkflowsFromConfigRequest,
    RegisterWorkflowsFromConfigResultFailure,
    RegisterWorkflowsFromConfigResultSuccess,
    RenameWorkflowRequest,
    RenameWorkflowResultFailure,
    RenameWorkflowResultSuccess,
    ResetWorkflowBranchRequest,
    ResetWorkflowBranchResultFailure,
    ResetWorkflowBranchResultSuccess,
    RunWorkflowFromRegistryRequest,
    RunWorkflowFromRegistryResultFailure,
    RunWorkflowFromRegistryResultSuccess,
    RunWorkflowFromScratchRequest,
    RunWorkflowFromScratchResultFailure,
    RunWorkflowFromScratchResultSuccess,
    RunWorkflowWithCurrentStateRequest,
    RunWorkflowWithCurrentStateResultFailure,
    RunWorkflowWithCurrentStateResultSuccess,
    SaveWorkflowFileFromSerializedFlowRequest,
    SaveWorkflowFileFromSerializedFlowResultFailure,
    SaveWorkflowFileFromSerializedFlowResultSuccess,
    SaveWorkflowRequest,
    SaveWorkflowResultFailure,
    SaveWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import (
    GriptapeNodes,
)
from griptape_nodes.retained_mode.managers.fitness_problems.workflows import (
    InvalidDependencyVersionStringProblem,
    InvalidLibraryVersionStringProblem,
    InvalidMetadataSchemaProblem,
    InvalidMetadataSectionCountProblem,
    InvalidTomlFormatProblem,
    LibraryNotRegisteredProblem,
    LibraryVersionBelowRequiredProblem,
    LibraryVersionLargeDifferenceProblem,
    LibraryVersionMajorMismatchProblem,
    LibraryVersionMinorDifferenceProblem,
    MissingCreationDateProblem,
    MissingLastModifiedDateProblem,
    MissingTomlSectionProblem,
    WorkflowNotFoundProblem,
)
from griptape_nodes.retained_mode.managers.os_manager import OSManager

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import TracebackType

    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands, SetLockNodeStateRequest
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem


T = TypeVar("T")

# Type aliases for workflow shape building
ParameterShapeInfo = dict[str, Any]  # Parameter metadata dict from _convert_parameter_to_minimal_dict
NodeParameterMap = dict[str, ParameterShapeInfo]  # {param_name: param_info}
WorkflowShapeNodes = dict[str, NodeParameterMap]  # {node_name: {param_name: param_info}}

logger = logging.getLogger("griptape_nodes")


class WorkflowRegistrationResult(NamedTuple):
    """Result of processing workflows for registration."""

    succeeded: list[str]
    failed: list[str]


class WorkflowManager:
    WORKFLOW_METADATA_HEADER: ClassVar[str] = "script"
    MAX_MINOR_VERSION_DEVIATION: ClassVar[int] = (
        100  # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1219 <- make the versioning enforcement softer after we get a release going
    )
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
        problems: list[WorkflowProblem] = field(default_factory=list)

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

    # Track referenced workflow import context stack
    class ReferencedWorkflowContext:
        """Context manager for tracking workflow import operations."""

        def __init__(self, manager: WorkflowManager, workflow_name: str):
            self.manager = manager
            self.workflow_name = workflow_name

        def __enter__(self) -> WorkflowManager.ReferencedWorkflowContext:
            self.manager._referenced_workflow_stack.append(self.workflow_name)
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
            self.manager._referenced_workflow_stack.pop()

    _referenced_workflow_stack: list[str] = field(default_factory=list)

    class WorkflowExecutionResult(NamedTuple):
        """Result of a workflow execution."""

        execution_successful: bool
        execution_details: str

    class SaveWorkflowScenario(StrEnum):
        """Scenarios for saving workflows."""

        FIRST_SAVE = "first_save"  # First save of new workflow
        OVERWRITE_EXISTING = "overwrite_existing"  # Save existing workflow to same name
        SAVE_AS = "save_as"  # Save existing workflow with new name
        SAVE_FROM_TEMPLATE = "save_from_template"  # Save from a template

    @dataclass
    class SaveWorkflowTargetInfo:
        """Target information for saving a workflow."""

        scenario: WorkflowManager.SaveWorkflowScenario  # Which save scenario we're in
        file_name: str  # Final resolved name to use
        file_path: Path  # Absolute path where file will be written
        relative_file_path: str  # Relative path for registry
        creation_date: datetime  # When workflow was originally created
        branched_from: str | None  # Workflow this was branched from (if any)

    def __init__(self, event_manager: EventManager) -> None:
        self._workflow_file_path_to_info = {}
        self._squelch_workflow_altered_count = 0
        self._referenced_workflow_stack = []
        self._workflows_loading_complete = asyncio.Event()

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
            MoveWorkflowRequest,
            self.on_move_workflow_request,
        )

        event_manager.assign_manager_to_request_type(
            SaveWorkflowRequest,
            self.on_save_workflow_request,
        )
        event_manager.assign_manager_to_request_type(
            SaveWorkflowFileFromSerializedFlowRequest,
            self.on_save_workflow_file_from_serialized_flow_request,
        )
        event_manager.assign_manager_to_request_type(LoadWorkflowMetadata, self.on_load_workflow_metadata_request)
        event_manager.assign_manager_to_request_type(
            PublishWorkflowRequest,
            self.on_publish_workflow_request,
        )
        event_manager.assign_manager_to_request_type(
            ImportWorkflowAsReferencedSubFlowRequest,
            self.on_import_workflow_as_referenced_sub_flow_request,
        )
        event_manager.assign_manager_to_request_type(
            ImportWorkflowRequest,
            self.on_import_workflow_request,
        )
        event_manager.assign_manager_to_request_type(
            BranchWorkflowRequest,
            self.on_branch_workflow_request,
        )
        event_manager.assign_manager_to_request_type(
            MergeWorkflowBranchRequest,
            self.on_merge_workflow_branch_request,
        )
        event_manager.assign_manager_to_request_type(
            ResetWorkflowBranchRequest,
            self.on_reset_workflow_branch_request,
        )
        event_manager.assign_manager_to_request_type(
            CompareWorkflowsRequest,
            self.on_compare_workflows_request,
        )
        event_manager.assign_manager_to_request_type(
            RegisterWorkflowsFromConfigRequest,
            self.on_register_workflows_from_config_request,
        )

    def has_current_referenced_workflow(self) -> bool:
        """Check if there is currently a referenced workflow context active."""
        return len(self._referenced_workflow_stack) > 0

    def get_current_referenced_workflow(self) -> str:
        """Get the current workflow source path from the context stack.

        Raises:
            IndexError: If no referenced workflow context is active.
        """
        return self._referenced_workflow_stack[-1]

    def on_libraries_initialization_complete(self) -> None:
        # All of the libraries have loaded, and any workflows they came with have been registered.
        # Discover workflows from both config and workspace.
        self._workflows_loading_complete.clear()

        try:
            default_workflow_section = "app_events.on_app_initialization_complete.workflows_to_register"
            config_mgr = GriptapeNodes.ConfigManager()

            workflows_to_register = []

            # Add from config
            config_workflows = config_mgr.get_config_value(default_workflow_section, default=[])
            workflows_to_register.extend(config_workflows)

            # Add from workspace (avoiding duplicates)
            workspace_path = config_mgr.workspace_path
            workflows_to_register.extend([workspace_path])

            # Register all discovered workflows at once if any were found
            self._process_workflows_for_registration(workflows_to_register)

            # Print it all out nicely.
            self.print_workflow_load_status()

            # Now remove any workflows that were missing files.
            paths_to_remove = set()
            for workflow_path, workflow_info in self._workflow_file_path_to_info.items():
                if workflow_info.status == WorkflowManager.WorkflowStatus.MISSING:
                    # Remove this file path from the config.
                    paths_to_remove.add(workflow_path.lower())

            if paths_to_remove:
                workflows_to_register = config_mgr.get_config_value(default_workflow_section)
                if workflows_to_register:
                    workflows_to_register = [
                        workflow for workflow in workflows_to_register if workflow.lower() not in paths_to_remove
                    ]
                    config_mgr.set_config_value(default_workflow_section, workflows_to_register)
        finally:
            self._workflows_loading_complete.set()

    def get_workflow_metadata(self, workflow_file_path: Path, block_name: str) -> list[re.Match[str]]:
        """Get the workflow metadata for a given workflow file path.

        Args:
            workflow_file_path (Path): The path to the workflow file.
            block_name (str): The name of the metadata block to search for.

        Returns:
            list[re.Match[str]]: A list of regex matches for the specified metadata block.

        """
        with workflow_file_path.open("r", encoding="utf-8") as file:
            workflow_content = file.read()

        # Find the metadata block.
        regex = r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"
        matches = list(
            filter(
                lambda m: m.group("type") == block_name,
                re.finditer(regex, workflow_content),
            )
        )

        return matches

    def print_workflow_load_status(self, min_status: WorkflowStatus = WorkflowStatus.FLAWED) -> None:  # noqa: PLR0915
        workflow_file_paths = self.get_workflows_attempted_to_load()
        workflow_infos = []
        for workflow_file_path in workflow_file_paths:
            workflow_info = self.get_workflow_info_for_attempted_load(workflow_file_path)
            workflow_infos.append(workflow_info)

        # Filter workflows to only show those at or worse than min_status
        all_statuses = list(self.WorkflowStatus)
        min_status_index = all_statuses.index(min_status)
        filtered_workflow_infos = [
            wf_info for wf_info in workflow_infos if all_statuses.index(wf_info.status) >= min_status_index
        ]

        # Sort workflows by severity (worst to best)
        filtered_workflow_infos.sort(key=lambda wf: all_statuses.index(wf.status), reverse=True)

        console = Console()

        # Check if the list is empty
        if not filtered_workflow_infos:
            empty_message = Text("No workflow information available", style="italic")
            panel = Panel(empty_message, title="Workflow Information", border_style="blue")
            console.print(panel)
            return

        # Add filter message if not showing all workflows
        if min_status != self.WorkflowStatus.GOOD:
            statuses_shown = all_statuses[min_status_index:]
            status_names = ", ".join(s.value for s in statuses_shown)
            filter_message = Text(
                f"Only displaying workflows with a fitness of {status_names}",
                style="italic yellow",
            )
            console.print(filter_message)
            console.print()

        # Create a table with three columns and row dividers
        table = Table(show_header=True, box=HEAVY_EDGE, show_lines=True, expand=True)
        table.add_column("Workflow", style="green", ratio=2)
        table.add_column("Problems", style="yellow", ratio=3)
        table.add_column("Dependencies", style="magenta", ratio=2)

        # Status emojis mapping
        status_emoji = {
            self.WorkflowStatus.GOOD: "[green]OK[/green]",
            self.WorkflowStatus.FLAWED: "[yellow]![/yellow]",
            self.WorkflowStatus.UNUSABLE: "[red]X[/red]",
            self.WorkflowStatus.MISSING: "[red]?[/red]",
        }

        # Status text mapping (colored)
        status_text = {
            self.WorkflowStatus.GOOD: "[green](GOOD)[/green]",
            self.WorkflowStatus.FLAWED: "[yellow](FLAWED)[/yellow]",
            self.WorkflowStatus.UNUSABLE: "[red](UNUSABLE)[/red]",
            self.WorkflowStatus.MISSING: "[red](MISSING)[/red]",
        }

        dependency_status_emoji = {
            self.WorkflowDependencyStatus.PERFECT: "[green]OK[/green]",
            self.WorkflowDependencyStatus.GOOD: "[green]GOOD[/green]",
            self.WorkflowDependencyStatus.CAUTION: "[yellow]CAUTION[/yellow]",
            self.WorkflowDependencyStatus.BAD: "[red]BAD[/red]",
            self.WorkflowDependencyStatus.MISSING: "[red]MISSING[/red]",
            self.WorkflowDependencyStatus.UNKNOWN: "[red]UNKNOWN[/red]",
        }

        # Add rows for each workflow info
        for wf_info in filtered_workflow_infos:
            # Workflow name column with emoji, name, colored status, and file path underneath
            emoji = status_emoji.get(wf_info.status, "ERR: Unknown/Unexpected Workflow Status")
            colored_status = status_text.get(wf_info.status, "(UNKNOWN)")
            name = wf_info.workflow_name if wf_info.workflow_name else "*UNKNOWN*"
            file_path = wf_info.workflow_path
            workflow_name_with_path = Text.from_markup(
                f"{emoji} - {name} {colored_status}\n[cyan dim]{file_path}[/cyan dim]"
            )
            workflow_name_with_path.overflow = "fold"

            # Problems column - collate by type
            if not wf_info.problems:
                problems = "No problems detected."
            else:
                # Group problems by type
                problems_by_type = defaultdict(list)
                for problem in wf_info.problems:
                    problems_by_type[type(problem)].append(problem)

                # Collate each group
                collated_strings = []
                for problem_class, instances in problems_by_type.items():
                    collated_display = problem_class.collate_problems_for_display(instances)
                    collated_strings.append(collated_display)

                # Format for display
                if len(collated_strings) == 1:
                    problems = collated_strings[0]
                else:
                    problems = "\n".join([f"{j + 1}. {problem}" for j, problem in enumerate(collated_strings)])

            # Dependencies column
            if wf_info.status == self.WorkflowStatus.MISSING or (
                wf_info.status == self.WorkflowStatus.UNUSABLE and not wf_info.workflow_dependencies
            ):
                dependencies = "[red]?[/red] UNKNOWN"
            else:
                dependencies = (
                    "\n".join(
                        f"{dependency_status_emoji.get(dep.status, '?')} - {dep.library_name} ({dep.version_requested}): {dep.status.value}"
                        for dep in wf_info.workflow_dependencies
                    )
                    if wf_info.workflow_dependencies
                    else "No dependencies"
                )

            table.add_row(
                workflow_name_with_path,
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

    async def _ensure_workflow_context_established(self) -> None:
        """Ensure there's a current workflow and flow context after workflow execution."""
        context_manager = GriptapeNodes.ContextManager()

        # First check: Do we have a current workflow? If not, that's a critical failure.
        if not context_manager.has_current_workflow():
            error_message = "Workflow execution completed but no current workflow is established in context"
            raise RuntimeError(error_message)

        # Second check: Do we have a current flow? If not, try to establish one.
        if not context_manager.has_current_flow():
            # Use the proper request to get the top-level flow
            from griptape_nodes.retained_mode.events.flow_events import (
                GetTopLevelFlowRequest,
                GetTopLevelFlowResultSuccess,
            )

            top_level_flow_request = GetTopLevelFlowRequest()
            top_level_flow_result = await GriptapeNodes.ahandle_request(top_level_flow_request)

            if (
                isinstance(top_level_flow_result, GetTopLevelFlowResultSuccess)
                and top_level_flow_result.flow_name is not None
            ):
                # Push the flow to the context stack permanently using FlowManager
                flow_manager = GriptapeNodes.FlowManager()
                flow_obj = flow_manager.get_flow_by_name(top_level_flow_result.flow_name)
                context_manager.push_flow(flow_obj)
                details = f"Workflow execution completed. Set '{top_level_flow_result.flow_name}' as current context."
                logger.debug(details)

            # If we still don't have a flow, that's a critical error
            if not context_manager.has_current_flow():
                error_message = "Workflow execution completed but no current flow context could be established"
                raise RuntimeError(error_message)

    async def run_workflow(self, relative_file_path: str) -> WorkflowExecutionResult:
        relative_file_path_obj = Path(relative_file_path)
        if relative_file_path_obj.is_absolute():
            complete_file_path = relative_file_path_obj
        else:
            complete_file_path = WorkflowRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        try:
            # Libraries are now loaded only on app initialization and explicit reload requests
            # Now execute the workflow.
            async with aiofiles.open(Path(complete_file_path), encoding="utf-8") as file:
                workflow_content = await file.read()
            exec(workflow_content)  # noqa: S102

            # After workflow execution, ensure there's always a current context by pushing
            # the top-level flow if the context is empty. This fixes regressions where
            # with Workflow Schema version 0.6.0+ workflows expect context to be established.
            await self._ensure_workflow_context_established()

        except Exception as e:
            return WorkflowManager.WorkflowExecutionResult(
                execution_successful=False,
                execution_details=f"Failed to run workflow on path '{complete_file_path}'. Exception: {e}",
            )
        return WorkflowManager.WorkflowExecutionResult(
            execution_successful=True,
            execution_details=f"Succeeded in running workflow on path '{complete_file_path}'.",
        )

    async def on_run_workflow_from_scratch_request(self, request: RunWorkflowFromScratchRequest) -> ResultPayload:
        # Squelch any ResultPayloads that indicate the workflow was changed, because we are loading it into a blank slate.
        with WorkflowManager.WorkflowSquelchContext(self):
            # Check if file path exists
            relative_file_path = request.file_path
            complete_file_path = WorkflowRegistry.get_complete_file_path(relative_file_path=relative_file_path)
            if not Path(complete_file_path).is_file():
                details = f"Failed to find file. Path '{complete_file_path}' doesn't exist."
                return RunWorkflowFromScratchResultFailure(result_details=details)

            # Start with a clean slate.
            clear_all_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
            clear_all_result = await GriptapeNodes.ahandle_request(clear_all_request)
            if not clear_all_result.succeeded():
                details = f"Failed to clear the existing object state when trying to run '{complete_file_path}'."
                return RunWorkflowFromScratchResultFailure(result_details=details)

            # Run the file, goddamn it
            execution_result = await self.run_workflow(relative_file_path=relative_file_path)
            if execution_result.execution_successful:
                return RunWorkflowFromScratchResultSuccess(result_details=execution_result.execution_details)

            logger.error(execution_result.execution_details)
            return RunWorkflowFromScratchResultFailure(result_details=execution_result.execution_details)

    async def on_run_workflow_with_current_state_request(
        self, request: RunWorkflowWithCurrentStateRequest
    ) -> ResultPayload:
        relative_file_path = request.file_path
        complete_file_path = WorkflowRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        if not Path(complete_file_path).is_file():
            details = f"Failed to find file. Path '{complete_file_path}' doesn't exist."
            return RunWorkflowWithCurrentStateResultFailure(result_details=details)
        execution_result = await self.run_workflow(relative_file_path=relative_file_path)

        if execution_result.execution_successful:
            return RunWorkflowWithCurrentStateResultSuccess(result_details=execution_result.execution_details)
        logger.error(execution_result.execution_details)
        return RunWorkflowWithCurrentStateResultFailure(result_details=execution_result.execution_details)

    async def on_run_workflow_from_registry_request(self, request: RunWorkflowFromRegistryRequest) -> ResultPayload:
        await self._workflows_loading_complete.wait()

        # get workflow from registry
        try:
            workflow = WorkflowRegistry.get_workflow_by_name(request.workflow_name)
        except KeyError:
            details = f"Failed to get workflow '{request.workflow_name}' from registry."
            return RunWorkflowFromRegistryResultFailure(result_details=details)

        # Update current context for workflow.
        context_warning = None
        if GriptapeNodes.ContextManager().has_current_workflow():
            context_warning = f"Started a new workflow '{request.workflow_name}' but a workflow '{GriptapeNodes.ContextManager().get_current_workflow_name()}' was already in the Current Context. Replacing the old with the new."

        # get file_path from workflow
        relative_file_path = workflow.file_path

        # Squelch any ResultPayloads that indicate the workflow was changed, because we are loading it.
        with WorkflowManager.WorkflowSquelchContext(self):
            if request.run_with_clean_slate:
                # Start with a clean slate.
                clear_all_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
                clear_all_result = await GriptapeNodes.ahandle_request(clear_all_request)
                if not clear_all_result.succeeded():
                    details = f"Failed to clear the existing object state when preparing to run workflow '{request.workflow_name}'."
                    return RunWorkflowFromRegistryResultFailure(result_details=details)

            # Let's run under the assumption that this Workflow will become our Current Context; if we fail, it will revert.
            GriptapeNodes.ContextManager().push_workflow(request.workflow_name)
            # run file
            execution_result = await self.run_workflow(relative_file_path=relative_file_path)

            if not execution_result.execution_successful:
                result_messages = []
                if context_warning:
                    result_messages.append(ResultDetail(message=context_warning, level=logging.WARNING))
                result_messages.append(ResultDetail(message=execution_result.execution_details, level=logging.ERROR))

                # Attempt to clear everything out, as we modified the engine state getting here.
                clear_all_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
                clear_all_result = await GriptapeNodes.ahandle_request(clear_all_request)

                # The clear-all above here wipes the ContextManager, so no need to do a pop_workflow().
                return RunWorkflowFromRegistryResultFailure(result_details=ResultDetails(*result_messages))

        # Success!
        result_messages = []
        if context_warning:
            result_messages.append(ResultDetail(message=context_warning, level=logging.WARNING))
        result_messages.append(ResultDetail(message=execution_result.execution_details, level=logging.DEBUG))
        return RunWorkflowFromRegistryResultSuccess(result_details=ResultDetails(*result_messages))

    def on_register_workflow_request(self, request: RegisterWorkflowRequest) -> ResultPayload:
        try:
            if isinstance(request.metadata, dict):
                request.metadata = WorkflowMetadata(**request.metadata)

            workflow = WorkflowRegistry.generate_new_workflow(metadata=request.metadata, file_path=request.file_name)
        except Exception as e:
            details = f"Failed to register workflow with name '{request.metadata.name}'. Error: {e}"
            return RegisterWorkflowResultFailure(result_details=details)
        return RegisterWorkflowResultSuccess(
            workflow_name=workflow.metadata.name,
            result_details=ResultDetails(
                message=f"Successfully registered workflow: {workflow.metadata.name}",
                level=logging.DEBUG,
            ),
        )

    def on_import_workflow_request(self, request: ImportWorkflowRequest) -> ResultPayload:
        # First, attempt to load metadata from the file
        load_metadata_request = LoadWorkflowMetadata(file_name=request.file_path)
        load_metadata_result = self.on_load_workflow_metadata_request(load_metadata_request)

        if not isinstance(load_metadata_result, LoadWorkflowMetadataResultSuccess):
            return ImportWorkflowResultFailure(result_details=load_metadata_result.result_details)

        # Check if workflow is already registered
        workflow_name = load_metadata_result.metadata.name
        if WorkflowRegistry.has_workflow_with_name(workflow_name):
            # Workflow already exists - no need to re-register
            return ImportWorkflowResultSuccess(
                workflow_name=workflow_name,
                result_details=f"Workflow '{workflow_name}' already exists - no need to re-import.",
            )

        # Now register the workflow with the extracted metadata
        register_request = RegisterWorkflowRequest(metadata=load_metadata_result.metadata, file_name=request.file_path)
        register_result = self.on_register_workflow_request(register_request)

        if not isinstance(register_result, RegisterWorkflowResultSuccess):
            return ImportWorkflowResultFailure(result_details=register_result.result_details)

        # Add the workflow to the user configuration
        try:
            full_path = WorkflowRegistry.get_complete_file_path(request.file_path)
            GriptapeNodes.ConfigManager().save_user_workflow_json(full_path)
        except Exception as e:
            details = f"Failed to add workflow '{register_result.workflow_name}' to user configuration: {e}"

            return ImportWorkflowResultFailure(result_details=details)

        return ImportWorkflowResultSuccess(
            workflow_name=register_result.workflow_name,
            result_details=ResultDetails(
                message=f"Successfully imported workflow: {register_result.workflow_name}", level=logging.INFO
            ),
        )

    async def on_list_all_workflows_request(self, _request: ListAllWorkflowsRequest) -> ResultPayload:
        await self._workflows_loading_complete.wait()

        try:
            workflows = WorkflowRegistry.list_workflows()
        except Exception:
            details = "Failed to list all workflows."
            return ListAllWorkflowsResultFailure(result_details=details)
        return ListAllWorkflowsResultSuccess(
            workflows=workflows, result_details=f"Successfully retrieved {len(workflows)} workflows."
        )

    def on_delete_workflows_request(self, request: DeleteWorkflowRequest) -> ResultPayload:
        try:
            workflow = WorkflowRegistry.delete_workflow_by_name(request.name)
        except Exception as e:
            details = f"Failed to remove workflow from registry with name '{request.name}'. Exception: {e}"
            return DeleteWorkflowResultFailure(result_details=details)
        config_manager = GriptapeNodes.ConfigManager()
        try:
            config_manager.delete_user_workflow(workflow.file_path)
        except Exception as e:
            details = f"Failed to remove workflow from user config with name '{request.name}'. Exception: {e}"
            return DeleteWorkflowResultFailure(result_details=details)
        # delete the actual file
        full_path = config_manager.workspace_path.joinpath(workflow.file_path)
        try:
            full_path.unlink()
        except Exception as e:
            details = f"Failed to delete workflow file with path '{workflow.file_path}'. Exception: {e}"
            return DeleteWorkflowResultFailure(result_details=details)
        return DeleteWorkflowResultSuccess(
            result_details=ResultDetails(message=f"Successfully deleted workflow: {request.name}", level=logging.INFO)
        )

    async def on_rename_workflow_request(self, request: RenameWorkflowRequest) -> ResultPayload:
        save_workflow_request = await GriptapeNodes.ahandle_request(
            SaveWorkflowRequest(file_name=request.requested_name)
        )

        if isinstance(save_workflow_request, SaveWorkflowResultFailure):
            details = f"Attempted to rename workflow '{request.workflow_name}' to '{request.requested_name}'. Failed while attempting to save."
            return RenameWorkflowResultFailure(result_details=details)

        delete_workflow_result = await GriptapeNodes.ahandle_request(DeleteWorkflowRequest(name=request.workflow_name))
        if isinstance(delete_workflow_result, DeleteWorkflowResultFailure):
            details = f"Attempted to rename workflow '{request.workflow_name}' to '{request.requested_name}'. Failed while attempting to remove the original file name from the registry."
            return RenameWorkflowResultFailure(result_details=details)

        return RenameWorkflowResultSuccess(
            result_details=ResultDetails(
                message=f"Successfully renamed workflow to: {request.requested_name}", level=logging.INFO
            )
        )

    def on_move_workflow_request(self, request: MoveWorkflowRequest) -> ResultPayload:  # noqa: PLR0911
        try:
            # Validate source workflow exists
            workflow = WorkflowRegistry.get_workflow_by_name(request.workflow_name)
        except KeyError:
            details = f"Failed to move workflow '{request.workflow_name}' because it does not exist."
            return MoveWorkflowResultFailure(result_details=details)

        config_manager = GriptapeNodes.ConfigManager()

        # Get current file path
        current_file_path = WorkflowRegistry.get_complete_file_path(workflow.file_path)
        if not Path(current_file_path).exists():
            details = (
                f"Failed to move workflow '{request.workflow_name}': File path '{current_file_path}' does not exist."
            )
            return MoveWorkflowResultFailure(result_details=details)

        # Clean and validate target directory
        target_directory = request.target_directory.strip().replace("\\", "/")
        target_directory = target_directory.removeprefix("/")  # Remove leading slash

        # Create target directory path
        target_dir_path = config_manager.workspace_path / target_directory

        try:
            # Create target directory if it doesn't exist
            target_dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            details = f"Failed to create target directory '{target_dir_path}': {e!s}"
            return MoveWorkflowResultFailure(result_details=details)

        # Create new file path
        workflow_filename = Path(workflow.file_path).name
        new_relative_path = str(Path(target_directory) / workflow_filename)
        new_absolute_path = config_manager.workspace_path / new_relative_path

        # Check if target file already exists
        if new_absolute_path.exists():
            details = (
                f"Failed to move workflow '{request.workflow_name}': Target file '{new_absolute_path}' already exists."
            )
            return MoveWorkflowResultFailure(result_details=details)

        try:
            # Move the file
            Path(current_file_path).rename(new_absolute_path)

            # Update workflow registry with new file path
            workflow.file_path = new_relative_path

            # Update configuration - remove old path and add new path
            config_manager.delete_user_workflow(workflow.file_path)
            config_manager.save_user_workflow_json(str(new_absolute_path))

        except OSError as e:
            error_messages = []
            main_error = f"Failed to move workflow file '{current_file_path}' to '{new_absolute_path}': {e!s}"
            error_messages.append(ResultDetail(message=main_error, level=logging.ERROR))

            # Attempt to rollback if file was moved but registry update failed
            if new_absolute_path.exists() and not Path(current_file_path).exists():
                try:
                    new_absolute_path.rename(current_file_path)
                    rollback_message = f"Rolled back file move for workflow '{request.workflow_name}'"
                    error_messages.append(ResultDetail(message=rollback_message, level=logging.INFO))
                except OSError:
                    rollback_failure = f"Failed to rollback file move for workflow '{request.workflow_name}'"
                    error_messages.append(ResultDetail(message=rollback_failure, level=logging.ERROR))

            return MoveWorkflowResultFailure(result_details=ResultDetails(*error_messages))
        except Exception as e:
            details = f"Failed to move workflow '{request.workflow_name}': {e!s}"
            return MoveWorkflowResultFailure(result_details=details)
        else:
            details = f"Successfully moved workflow '{request.workflow_name}' to '{new_relative_path}'"
            return MoveWorkflowResultSuccess(
                moved_file_path=new_relative_path, result_details=ResultDetails(message=details, level=logging.INFO)
            )

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
                problems=[WorkflowNotFoundProblem()],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}. Failed because no file could be found at that path."
            return LoadWorkflowMetadataResultFailure(result_details=details)

        # Find the metadata block.
        block_name = WorkflowManager.WORKFLOW_METADATA_HEADER
        matches = self.get_workflow_metadata(complete_file_path, block_name=block_name)
        if len(matches) != 1:
            self._workflow_file_path_to_info[str(str_path)] = WorkflowManager.WorkflowInfo(
                status=WorkflowManager.WorkflowStatus.UNUSABLE,
                workflow_path=str_path,
                workflow_name=None,
                workflow_dependencies=[],
                problems=[InvalidMetadataSectionCountProblem(section_name=block_name, count=len(matches))],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed as it had {len(matches)} sections titled '{block_name}', and we expect exactly 1 such section."
            return LoadWorkflowMetadataResultFailure(result_details=details)

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
                problems=[InvalidTomlFormatProblem(error_message=str(err))],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed because the metadata was not valid TOML: {err}"
            return LoadWorkflowMetadataResultFailure(result_details=details)

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
                problems=[MissingTomlSectionProblem(section_path=f"[{tool_header}.{griptape_nodes_header}]")],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed because the '[{tool_header}.{griptape_nodes_header}]' section could not be found: {err}"
            return LoadWorkflowMetadataResultFailure(result_details=details)

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
                    InvalidMetadataSchemaProblem(
                        section_path=f"[{tool_header}.{griptape_nodes_header}]", error_message=str(err)
                    )
                ],
            )
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed because the metadata in the '[{tool_header}.{griptape_nodes_header}]' section did not match the requisite schema with error: {err}"
            return LoadWorkflowMetadataResultFailure(result_details=details)

        # We have valid dependencies, etc.
        # TODO: validate schema versions, engine versions: https://github.com/griptape-ai/griptape-nodes/issues/617
        problems = []
        had_critical_error = False

        # Confirm dates are correct.
        if workflow_metadata.creation_date is None:
            # Assign it to the epoch start and flag it as a warning.
            workflow_metadata.creation_date = WorkflowManager.EPOCH_START
            problems.append(MissingCreationDateProblem(default_date=str(WorkflowManager.EPOCH_START)))
        if workflow_metadata.last_modified_date is None:
            # Assign it to the epoch start and flag it as a warning.
            workflow_metadata.last_modified_date = WorkflowManager.EPOCH_START
            problems.append(MissingLastModifiedDateProblem(default_date=str(WorkflowManager.EPOCH_START)))

        # Get list of registered libraries once (silent check - no error logging)
        list_libraries_request = ListRegisteredLibrariesRequest()
        list_libraries_result = GriptapeNodes.LibraryManager().on_list_registered_libraries_request(
            list_libraries_request
        )

        if not isinstance(list_libraries_result, ListRegisteredLibrariesResultSuccess):
            # Should not happen, but handle gracefully - treat as no libraries registered
            registered_libraries = []
        else:
            registered_libraries = list_libraries_result.libraries

        dependency_infos = []
        for node_library_referenced in workflow_metadata.node_libraries_referenced:
            library_name = node_library_referenced.library_name
            desired_version_str = node_library_referenced.library_version
            try:
                desired_version = semver.VersionInfo.parse(desired_version_str)
            except Exception:
                had_critical_error = True
                problems.append(
                    InvalidDependencyVersionStringProblem(library_name=library_name, version_string=desired_version_str)
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
            # Check if library is registered (silent check - no error logging)
            if library_name not in registered_libraries:
                # Library not registered
                had_critical_error = True
                problems.append(LibraryNotRegisteredProblem(library_name=library_name))
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

            # Get library metadata (we know library is registered, so no error logging)
            library_metadata_request = GetLibraryMetadataRequest(library=library_name)
            library_metadata_result = GriptapeNodes.LibraryManager().get_library_metadata_request(
                library_metadata_request
            )

            if not isinstance(library_metadata_result, GetLibraryMetadataResultSuccess):
                # Should not happen since we verified library is registered, but handle gracefully
                had_critical_error = True
                problems.append(LibraryNotRegisteredProblem(library_name=library_name))
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
            library_metadata = library_metadata_result.metadata
            library_version_str = library_metadata.library_version
            try:
                library_version = semver.VersionInfo.parse(library_version_str)
            except Exception:
                had_critical_error = True
                problems.append(
                    InvalidLibraryVersionStringProblem(library_name=library_name, version_string=library_version_str)
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
                        LibraryVersionBelowRequiredProblem(
                            library_name=library_name,
                            current_version=str(library_version),
                            required_version=str(desired_version),
                        )
                    )
                    status = WorkflowManager.WorkflowDependencyStatus.BAD
                    had_critical_error = True
                elif delta > WorkflowManager.MAX_MINOR_VERSION_DEVIATION:
                    problems.append(
                        LibraryVersionLargeDifferenceProblem(
                            library_name=library_name,
                            workflow_version=str(desired_version),
                            current_version=str(library_version),
                        )
                    )
                    status = WorkflowManager.WorkflowDependencyStatus.BAD
                    had_critical_error = True
                else:
                    problems.append(
                        LibraryVersionMinorDifferenceProblem(
                            library_name=library_name,
                            workflow_version=str(desired_version),
                            current_version=str(library_version),
                        )
                    )
                    status = WorkflowManager.WorkflowDependencyStatus.CAUTION
            else:
                problems.append(
                    LibraryVersionMajorMismatchProblem(
                        library_name=library_name,
                        workflow_version=str(desired_version),
                        current_version=str(library_version),
                    )
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

        # Check for workflow version-based compatibility issues and add to problems
        workflow_version_issues = GriptapeNodes.VersionCompatibilityManager().check_workflow_version_compatibility(
            workflow_metadata
        )
        for issue in workflow_version_issues:
            problems.append(issue.problem)
            if issue.severity == WorkflowManager.WorkflowStatus.UNUSABLE:
                had_critical_error = True

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
        return LoadWorkflowMetadataResultSuccess(
            metadata=workflow_metadata, result_details="Workflow metadata loaded successfully."
        )

    def register_workflows_from_config(self, config_section: str) -> None:
        workflows_to_register = GriptapeNodes.ConfigManager().get_config_value(config_section)
        if workflows_to_register:
            self.register_list_of_workflows(workflows_to_register)

    def register_list_of_workflows(self, workflows_to_register: list[str]) -> None:
        self._process_workflows_for_registration(workflows_to_register)

    def _register_workflow(self, workflow_to_register: str) -> bool:
        """Registers a workflow from a file.

        Args:
            config_mgr: The ConfigManager instance to use for path resolution.
            workflow_mgr: The WorkflowManager instance to use for workflow registration.
            workflow_to_register: The path to the workflow file to register.

        Returns:
            bool: True if the workflow was successfully registered, False otherwise.
        """
        # Presently, this will not fail if a workflow with that name is already registered. That failure happens with a later check.
        # However, the table of WorkflowInfo DOES get updated in this request, which may present a confusing state of affairs to the user.
        # On one hand, we want the user to know how a specific workflow fared, but also not let them think it was registered when it wasn't.
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/996

        # Attempt to extract the metadata out of the workflow.
        load_metadata_request = LoadWorkflowMetadata(file_name=str(workflow_to_register))
        load_metadata_result = self.on_load_workflow_metadata_request(load_metadata_request)
        if not load_metadata_result.succeeded():
            # SKIP IT
            return False

        if not isinstance(load_metadata_result, LoadWorkflowMetadataResultSuccess):
            err_str = (
                f"Attempted to register workflow '{workflow_to_register}', but failed to extract metadata. SKIPPING IT."
            )
            logger.error(err_str)
            return False

        workflow_metadata = load_metadata_result.metadata

        # Prepend the image paths appropriately.
        if workflow_metadata.image is not None:
            if workflow_metadata.is_griptape_provided:
                workflow_metadata.image = workflow_metadata.image
            else:
                # For user workflows, the image should be just the filename, not a full path
                # The frontend now sends just filenames, so we don't need to prepend the workspace path
                workflow_metadata.image = workflow_metadata.image

        # Register it as a success.
        workflow_register_request = RegisterWorkflowRequest(
            metadata=workflow_metadata, file_name=str(workflow_to_register)
        )
        workflow_register_result = GriptapeNodes.handle_request(workflow_register_request)
        if not isinstance(workflow_register_result, RegisterWorkflowResultSuccess):
            err_str = f"Error attempting to register workflow '{workflow_to_register}': {workflow_register_result}. SKIPPING IT."
            logger.error(err_str)
            return False

        return True

    class WriteWorkflowFileResult(NamedTuple):
        """Result of writing a workflow file."""

        success: bool
        error_details: str

    async def _write_workflow_file(self, file_path: Path, content: str, file_name: str) -> WriteWorkflowFileResult:
        """Write workflow content to file with proper validation and error handling.

        Args:
            file_path: Path where to write the file
            content: Content to write
            file_name: Name for error messages

        Returns:
            WriteWorkflowFileResult with success status and error details if failed
        """
        # Check disk space before any file system operations
        config_manager = GriptapeNodes.ConfigManager()
        min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_workflows")
        if not OSManager.check_available_disk_space(file_path.parent, min_space_gb):
            error_msg = OSManager.format_disk_space_error(file_path.parent)
            details = f"Attempted to save workflow '{file_name}' (requires {min_space_gb:.1f} GB). Failed due to insufficient disk space: {error_msg}"
            return self.WriteWorkflowFileResult(success=False, error_details=details)

        # Create directory structure
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            details = f"Attempted to save workflow '{file_name}'. Failed when creating directory structure: {e}"
            return self.WriteWorkflowFileResult(success=False, error_details=details)

        # Write the file content
        try:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                await file.write(content)
        except OSError as e:
            details = f"Attempted to save workflow '{file_name}'. Failed when writing file content: {e}"
            return self.WriteWorkflowFileResult(success=False, error_details=details)

        return self.WriteWorkflowFileResult(success=True, error_details="")

    async def on_save_workflow_request(self, request: SaveWorkflowRequest) -> ResultPayload:
        # Determine save target (file path, name, metadata)
        context_manager = GriptapeNodes.ContextManager()
        current_workflow_name = (
            context_manager.get_current_workflow_name() if context_manager.has_current_workflow() else None
        )

        try:
            save_target = self._determine_save_target(
                requested_file_name=request.file_name,
                current_workflow_name=current_workflow_name,
            )
        except ValueError as e:
            details = f"Attempted to save workflow. Failed when determining save target: {e}"
            return SaveWorkflowResultFailure(result_details=details)

        file_name = save_target.file_name
        file_path = save_target.file_path
        relative_file_path = save_target.relative_file_path
        creation_date = save_target.creation_date
        branched_from = save_target.branched_from

        logger.info(
            "Save workflow: scenario=%s, file_name=%s, file_path=%s, branched_from=%s",
            save_target.scenario.value,
            file_name,
            str(file_path),
            branched_from if branched_from else "None",
        )

        # Serialize the current workflow state
        top_level_flow_request = GetTopLevelFlowRequest()
        top_level_flow_result = await GriptapeNodes.ahandle_request(top_level_flow_request)
        if not isinstance(top_level_flow_result, GetTopLevelFlowResultSuccess):
            details = f"Attempted to save workflow '{relative_file_path}'. Failed when requesting top level flow."
            return SaveWorkflowResultFailure(result_details=details)

        top_level_flow_name = top_level_flow_result.flow_name
        serialized_flow_request = SerializeFlowToCommandsRequest(
            flow_name=top_level_flow_name, include_create_flow_command=True
        )
        serialized_flow_result = await GriptapeNodes.ahandle_request(serialized_flow_request)
        if not isinstance(serialized_flow_result, SerializeFlowToCommandsResultSuccess):
            details = f"Attempted to save workflow '{relative_file_path}'. Failed when serializing flow."
            return SaveWorkflowResultFailure(result_details=details)

        serialized_flow_commands = serialized_flow_result.serialized_flow_commands

        # Extract workflow shape if possible
        workflow_shape = None
        try:
            workflow_shape_dict = self.extract_workflow_shape(workflow_name=file_name)
            workflow_shape = WorkflowShape(inputs=workflow_shape_dict["input"], outputs=workflow_shape_dict["output"])
        except ValueError:
            # If we can't extract workflow shape, continue without it
            pass

        # Use the standalone request to save the workflow file
        # Use pickle_control_flow_result from request if provided, otherwise use False (default)
        pickle_control_flow_result = (
            request.pickle_control_flow_result if request.pickle_control_flow_result is not None else False
        )
        save_file_request = SaveWorkflowFileFromSerializedFlowRequest(
            serialized_flow_commands=serialized_flow_commands,
            file_name=file_name,
            creation_date=creation_date,
            image_path=request.image_path,
            execution_flow_name=top_level_flow_name,
            branched_from=branched_from,
            workflow_shape=workflow_shape,
            file_path=str(file_path),
            pickle_control_flow_result=pickle_control_flow_result,
        )
        save_file_result = await self.on_save_workflow_file_from_serialized_flow_request(save_file_request)

        if not isinstance(save_file_result, SaveWorkflowFileFromSerializedFlowResultSuccess):
            details = f"Attempted to save workflow '{relative_file_path}'. Failed during file generation: {save_file_result.result_details}"
            return SaveWorkflowResultFailure(result_details=details)

        # Use the metadata returned by the save operation
        workflow_metadata = save_file_result.workflow_metadata

        # save the created workflow as an entry in the JSON config file.
        registered_workflows = WorkflowRegistry.list_workflows()
        if file_name not in registered_workflows:
            # Only add to config if it's in the workspace directory (not an external file)
            if not Path(relative_file_path).is_absolute():
                try:
                    GriptapeNodes.ConfigManager().save_user_workflow_json(str(file_path))
                except OSError as e:
                    details = f"Attempted to save workflow '{file_name}'. Failed when saving configuration: {e}"
                    return SaveWorkflowResultFailure(result_details=details)
            WorkflowRegistry.generate_new_workflow(metadata=workflow_metadata, file_path=relative_file_path)
        # Update existing workflow's metadata in the registry
        existing_workflow = WorkflowRegistry.get_workflow_by_name(file_name)
        existing_workflow.metadata = workflow_metadata
        details = f"Successfully saved workflow to: {save_file_result.file_path}"
        return SaveWorkflowResultSuccess(
            file_path=save_file_result.file_path, result_details=ResultDetails(message=details, level=logging.INFO)
        )

    def _determine_save_target(
        self, requested_file_name: str | None, current_workflow_name: str | None
    ) -> SaveWorkflowTargetInfo:
        """Determine the target file path, name, and metadata for saving a workflow.

        Args:
            requested_file_name: The name the user wants to save as (can be None)
            current_workflow_name: The workflow currently loaded in context (can be None)

        Returns:
            SaveWorkflowTargetInfo with all information needed to save the workflow

        Raises:
            ValueError: If workflow registry lookups fail or produce inconsistent state
        """
        # Look up workflows in registry
        target_workflow = None
        if requested_file_name and WorkflowRegistry.has_workflow_with_name(requested_file_name):
            target_workflow = WorkflowRegistry.get_workflow_by_name(requested_file_name)

        current_workflow = None
        if current_workflow_name and WorkflowRegistry.has_workflow_with_name(current_workflow_name):
            current_workflow = WorkflowRegistry.get_workflow_by_name(current_workflow_name)

        # Determine scenario and build target info
        if (target_workflow and target_workflow.metadata.is_template) or (
            current_workflow and current_workflow.metadata.is_template
        ):
            # Template workflows always create new copies with unique names
            scenario = WorkflowManager.SaveWorkflowScenario.SAVE_FROM_TEMPLATE
            template_workflow = target_workflow or current_workflow
            if template_workflow is None:
                msg = "Save From Template scenario requires either target_workflow or current_workflow to be present"
                raise ValueError(msg)
            base_name = requested_file_name if requested_file_name else template_workflow.metadata.name

            # Find unique filename
            curr_idx = 1
            while True:
                candidate_name = f"{base_name}_{curr_idx}"
                candidate_path = GriptapeNodes.ConfigManager().workspace_path.joinpath(f"{candidate_name}.py")
                if not candidate_path.exists():
                    break
                curr_idx += 1

            file_name = candidate_name
            creation_date = datetime.now(tz=UTC)
            branched_from = None
            relative_file_path = f"{file_name}.py"
            file_path = GriptapeNodes.ConfigManager().workspace_path.joinpath(relative_file_path)

        elif target_workflow:
            # Requested name exists in registry → overwrite it
            scenario = WorkflowManager.SaveWorkflowScenario.OVERWRITE_EXISTING
            file_name = target_workflow.metadata.name
            creation_date = target_workflow.metadata.creation_date
            branched_from = target_workflow.metadata.branched_from
            relative_file_path = target_workflow.file_path
            file_path = Path(WorkflowRegistry.get_complete_file_path(relative_file_path))

        elif requested_file_name and current_workflow:
            # Requested name doesn't exist but we have a current workflow → Save As
            scenario = WorkflowManager.SaveWorkflowScenario.SAVE_AS
            file_name = requested_file_name
            creation_date = current_workflow.metadata.creation_date
            branched_from = current_workflow.metadata.branched_from
            relative_file_path = f"{file_name}.py"
            file_path = GriptapeNodes.ConfigManager().workspace_path.joinpath(relative_file_path)

        else:
            # No requested name or no current workflow → first save
            scenario = WorkflowManager.SaveWorkflowScenario.FIRST_SAVE
            file_name = requested_file_name if requested_file_name else datetime.now(tz=UTC).strftime("%d.%m_%H.%M")
            creation_date = datetime.now(tz=UTC)
            branched_from = None
            relative_file_path = f"{file_name}.py"
            file_path = GriptapeNodes.ConfigManager().workspace_path.joinpath(relative_file_path)

        # Ensure creation date is valid (backcompat)
        if (creation_date is None) or (creation_date == WorkflowManager.EPOCH_START):
            creation_date = datetime.now(tz=UTC)

        return WorkflowManager.SaveWorkflowTargetInfo(
            scenario=scenario,
            file_name=file_name,
            file_path=file_path,
            relative_file_path=relative_file_path,
            creation_date=creation_date,
            branched_from=branched_from,
        )

    async def on_save_workflow_file_from_serialized_flow_request(
        self, request: SaveWorkflowFileFromSerializedFlowRequest
    ) -> ResultPayload:
        """Save a workflow file from serialized flow commands without registry overhead."""
        # Determine file path
        if request.file_path:
            # Use provided file path
            file_path = Path(request.file_path)
        else:
            # Default to workspace path
            relative_file_path = f"{request.file_name}.py"
            file_path = GriptapeNodes.ConfigManager().workspace_path.joinpath(relative_file_path)

        # Use provided creation date or default to current time
        creation_date = request.creation_date
        if creation_date is None:
            creation_date = datetime.now(tz=UTC)

        # Generate metadata from the serialized commands
        try:
            workflow_metadata = self._generate_workflow_metadata_from_commands(
                serialized_flow_commands=request.serialized_flow_commands,
                file_name=request.file_name,
                creation_date=creation_date,
                image_path=request.image_path,
                branched_from=request.branched_from,
                workflow_shape=request.workflow_shape,
            )
        except Exception as err:
            details = f"Attempted to save workflow file '{request.file_name}' from serialized flow commands. Failed during metadata generation: {err}"
            return SaveWorkflowFileFromSerializedFlowResultFailure(result_details=details)

        # Use provided execution flow name or default to file name
        execution_flow_name = request.execution_flow_name
        if execution_flow_name is None:
            execution_flow_name = request.file_name

        # Generate the workflow file content
        try:
            final_code_output = self._generate_workflow_file_content(
                serialized_flow_commands=request.serialized_flow_commands,
                workflow_metadata=workflow_metadata,
                pickle_control_flow_result=request.pickle_control_flow_result,
            )
        except Exception as err:
            details = f"Attempted to save workflow file '{request.file_name}' from serialized flow commands. Failed during content generation: {err}"
            return SaveWorkflowFileFromSerializedFlowResultFailure(result_details=details)

        # Write the workflow file
        write_result = await self._write_workflow_file(file_path, final_code_output, request.file_name)
        if not write_result.success:
            return SaveWorkflowFileFromSerializedFlowResultFailure(result_details=write_result.error_details)

        details = f"Successfully saved workflow file at: {file_path}"
        return SaveWorkflowFileFromSerializedFlowResultSuccess(
            file_path=str(file_path),
            workflow_metadata=workflow_metadata,
            result_details=ResultDetails(message=details, level=logging.INFO),
        )

    def _generate_workflow_metadata_from_commands(  # noqa: PLR0913
        self,
        serialized_flow_commands: SerializedFlowCommands,
        file_name: str,
        creation_date: datetime,
        image_path: str | None = None,
        branched_from: str | None = None,
        workflow_shape: WorkflowShape | None = None,
    ) -> WorkflowMetadata:
        """Generate workflow metadata from serialized commands."""
        # Get the engine version
        engine_version_request = GetEngineVersionRequest()
        engine_version_result = GriptapeNodes.handle_request(request=engine_version_request)
        if not isinstance(engine_version_result, GetEngineVersionResultSuccess):
            details = f"Failed getting the engine version for workflow '{file_name}'."
            raise TypeError(details)

        engine_version_success = cast("GetEngineVersionResultSuccess", engine_version_result)
        engine_version = f"{engine_version_success.major}.{engine_version_success.minor}.{engine_version_success.patch}"

        # Create the Workflow Metadata header
        workflows_referenced = None
        if serialized_flow_commands.node_dependencies.referenced_workflows:
            workflows_referenced = list(serialized_flow_commands.node_dependencies.referenced_workflows)

        return WorkflowMetadata(
            name=str(file_name),
            schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
            engine_version_created_with=engine_version,
            node_libraries_referenced=list(serialized_flow_commands.node_dependencies.libraries),
            node_types_used=serialized_flow_commands.node_types_used,
            workflows_referenced=workflows_referenced,
            creation_date=creation_date,
            last_modified_date=datetime.now(tz=UTC),
            branched_from=branched_from,
            workflow_shape=workflow_shape,
            image=image_path,
        )

    def _generate_workflow_file_content(  # noqa: PLR0912, PLR0915, C901
        self,
        serialized_flow_commands: SerializedFlowCommands,
        workflow_metadata: WorkflowMetadata,
        *,
        pickle_control_flow_result: bool = False,
    ) -> str:
        """Generate workflow file content from serialized commands and metadata."""
        metadata_block = self._generate_workflow_metadata_header(workflow_metadata=workflow_metadata)
        if metadata_block is None:
            details = f"Failed to generate metadata block for workflow '{workflow_metadata.name}'."
            raise ValueError(details)

        import_recorder = ImportRecorder()
        import_recorder.add_from_import("griptape_nodes.retained_mode.griptape_nodes", "GriptapeNodes")

        # Add imports from node dependencies
        for import_dep in serialized_flow_commands.node_dependencies.imports:
            if import_dep.class_name:
                import_recorder.add_from_import(import_dep.module, import_dep.class_name)
            else:
                import_recorder.add_import(import_dep.module)

        ast_container = ASTContainer()

        prereq_code = self._generate_workflow_run_prerequisite_code(
            workflow_name=workflow_metadata.name, import_recorder=import_recorder
        )
        for node in prereq_code:
            ast_container.add_node(node)

        # Generate unique values code AST node
        unique_values_node = self._generate_unique_values_code(
            unique_parameter_uuid_to_values=serialized_flow_commands.unique_parameter_uuid_to_values,
            prefix="top_level",
            import_recorder=import_recorder,
        )
        ast_container.add_node(unique_values_node)

        # Keep track of each flow and node index we've created
        flow_creation_index = 0

        # See if this serialized flow has a flow initialization command; if it does, we'll need to insert that
        flow_initialization_command = serialized_flow_commands.flow_initialization_command

        match flow_initialization_command:
            case CreateFlowRequest():
                # Generate create flow context AST module
                create_flow_context_module = self._generate_create_flow(
                    flow_initialization_command, import_recorder, flow_creation_index
                )
                for node in create_flow_context_module.body:
                    ast_container.add_node(node)
            case ImportWorkflowAsReferencedSubFlowRequest():
                # Generate import workflow context AST module
                import_workflow_context_module = self._generate_import_workflow(
                    flow_initialization_command, import_recorder, flow_creation_index
                )
                for node in import_workflow_context_module.body:
                    ast_container.add_node(node)
            case None:
                # No initialization command, deserialize into current context
                pass

        # Generate assign flow context AST node, if we have any children commands
        # Skip content generation for referenced workflows - they should only have the import command
        is_referenced_workflow = isinstance(flow_initialization_command, ImportWorkflowAsReferencedSubFlowRequest)
        has_content_to_serialize = (
            len(serialized_flow_commands.serialized_node_commands) > 0
            or len(serialized_flow_commands.serialized_connections) > 0
            or len(serialized_flow_commands.set_parameter_value_commands) > 0
            or len(serialized_flow_commands.sub_flows_commands) > 0
            or len(serialized_flow_commands.set_lock_commands_per_node) > 0
        )

        if not is_referenced_workflow and has_content_to_serialize:
            # Keep track of all of the nodes we create and the generated variable names for them
            node_uuid_to_node_variable_name: dict[SerializedNodeCommands.NodeUUID, str] = {}

            # Create the "with..." statement
            assign_flow_context_node = self._generate_assign_flow_context(
                flow_initialization_command=flow_initialization_command, flow_creation_index=flow_creation_index
            )

            # Generate nodes in flow AST node. This will create the node and apply all element modifiers
            nodes_in_flow = self._generate_nodes_in_flow(
                serialized_flow_commands, import_recorder, node_uuid_to_node_variable_name
            )

            # Add the nodes to the body of the Current Context flow's "with" statement
            assign_flow_context_node.body.extend(nodes_in_flow)

            # Process sub-flows - for each sub-flow, generate its initialization command
            for sub_flow_index, sub_flow_commands in enumerate(serialized_flow_commands.sub_flows_commands):
                sub_flow_creation_index = flow_creation_index + 1 + sub_flow_index

                # Generate initialization command for the sub-flow
                sub_flow_initialization_command = sub_flow_commands.flow_initialization_command
                if sub_flow_initialization_command is not None:
                    match sub_flow_initialization_command:
                        case CreateFlowRequest():
                            sub_flow_create_node = self._generate_create_flow(
                                sub_flow_initialization_command, import_recorder, sub_flow_creation_index
                            )
                            assign_flow_context_node.body.append(cast("ast.stmt", sub_flow_create_node))
                        case ImportWorkflowAsReferencedSubFlowRequest():
                            sub_flow_import_node = self._generate_import_workflow(
                                sub_flow_initialization_command, import_recorder, sub_flow_creation_index
                            )
                            assign_flow_context_node.body.append(cast("ast.stmt", sub_flow_import_node))

            # Now generate the connection code and add it to the flow context
            connection_asts = self._generate_connections_code(
                serialized_connections=serialized_flow_commands.serialized_connections,
                node_uuid_to_node_variable_name=node_uuid_to_node_variable_name,
                import_recorder=import_recorder,
            )
            assign_flow_context_node.body.extend(connection_asts)

            # Generate parameter values
            set_parameter_value_asts = self._generate_set_parameter_value_code(
                set_parameter_value_commands=serialized_flow_commands.set_parameter_value_commands,
                lock_commands=serialized_flow_commands.set_lock_commands_per_node,
                node_uuid_to_node_variable_name=node_uuid_to_node_variable_name,
                unique_values_dict_name="top_level_unique_values_dict",
                import_recorder=import_recorder,
            )
            assign_flow_context_node.body.extend(set_parameter_value_asts)

            ast_container.add_node(assign_flow_context_node)

        # Generate workflow execution code
        workflow_execution_code = self._generate_workflow_execution(
            import_recorder=import_recorder,
            workflow_metadata=workflow_metadata,
            pickle_control_flow_result=pickle_control_flow_result,
        )
        if workflow_execution_code is not None:
            for node in workflow_execution_code:
                ast_container.add_node(node)

        # Generate final code from ASTContainer
        ast_output = "\n\n".join([ast.unparse(node) for node in ast_container.get_ast()])
        import_output = import_recorder.generate_imports()
        return f"{metadata_block}\n\n{import_output}\n\n{ast_output}\n"

    def _replace_workflow_metadata_header(self, workflow_content: str, new_metadata: WorkflowMetadata) -> str | None:
        """Replace the metadata header in a workflow file with new metadata.

        Args:
            workflow_content: The full content of the workflow file
            new_metadata: The new metadata to replace the existing header with

        Returns:
            The workflow content with updated metadata header, or None if replacement failed
        """
        import re

        # Generate the new metadata header
        new_metadata_header = self._generate_workflow_metadata_header(new_metadata)
        if new_metadata_header is None:
            return None

        # Replace the metadata block using regex
        metadata_pattern = r"(# /// script\n)(.*?)(# ///)"
        updated_content = re.sub(metadata_pattern, new_metadata_header, workflow_content, flags=re.DOTALL)

        return updated_content

    def _generate_workflow_metadata_header(self, workflow_metadata: WorkflowMetadata) -> str | None:
        try:
            toml_doc = tomlkit.document()
            toml_doc.add("dependencies", tomlkit.item([]))
            griptape_tool_table = tomlkit.table()
            # Strip out the Nones since TOML doesn't like those
            # WorkflowShape is now serialized as JSON string by Pydantic field_serializer;
            # this preserves the nil/null/None values that we WANT, but for all of the
            # Python-related Nones, TOML will flip out if they are not stripped.
            metadata_dict = workflow_metadata.model_dump(exclude_none=True)
            for key, value in metadata_dict.items():
                griptape_tool_table.add(key=key, value=value)
            toml_doc["tool"] = tomlkit.table()
            toml_doc["tool"]["griptape-nodes"] = griptape_tool_table  # type: ignore (this is the only way I could find to get tomlkit to do the dotted notation correctly)
        except Exception as err:
            details = f"Failed to get metadata into TOML format: {err}."
            logger.error(details)
            return None

        # Format the metadata block with comment markers for each line
        toml_lines = tomlkit.dumps(toml_doc).split("\n")
        commented_toml_lines = ["# " + line for line in toml_lines]

        # Create the complete metadata block
        header = f"# /// {WorkflowManager.WORKFLOW_METADATA_HEADER}"
        metadata_lines = [header]
        metadata_lines.extend(commented_toml_lines)
        metadata_lines.append("# ///")
        metadata_block = "\n".join(metadata_lines)

        return metadata_block

    def _generate_workflow_execution(
        self,
        import_recorder: ImportRecorder,
        workflow_metadata: WorkflowMetadata,
        *,
        pickle_control_flow_result: bool = False,
    ) -> list[ast.AST] | None:
        """Generates execute_workflow(...) and the __main__ guard."""
        # Use workflow shape from metadata if available, otherwise skip execution block
        if workflow_metadata.workflow_shape is None:
            logger.debug("Workflow shape does not have required Start or End Nodes. Skipping local execution block.")
            return None

        # Convert WorkflowShape to dict format expected by the rest of the method
        workflow_shape = {
            "input": workflow_metadata.workflow_shape.inputs,
            "output": workflow_metadata.workflow_shape.outputs,
        }

        # === imports ===
        import_recorder.add_import("argparse")
        import_recorder.add_import("asyncio")
        import_recorder.add_import("json")
        import_recorder.add_from_import(
            "griptape_nodes.bootstrap.workflow_executors.local_workflow_executor", "LocalWorkflowExecutor"
        )
        import_recorder.add_from_import(
            "griptape_nodes.bootstrap.workflow_executors.workflow_executor", "WorkflowExecutor"
        )
        import_recorder.add_from_import("griptape_nodes.drivers.storage.storage_backend", "StorageBackend")

        # === 1) build the `def execute_workflow(input: dict, storage_backend: str = StorageBackend.LOCAL, workflow_executor: WorkflowExecutor | None = None, pickle_control_flow_result: bool = False) -> dict | None:` ===
        #   args
        arg_input = ast.arg(arg="input", annotation=ast.Name(id="dict", ctx=ast.Load()))
        arg_storage_backend = ast.arg(arg="storage_backend", annotation=ast.Name(id="str", ctx=ast.Load()))
        arg_workflow_executor = ast.arg(
            arg="workflow_executor",
            annotation=ast.BinOp(
                left=ast.Name(id="WorkflowExecutor", ctx=ast.Load()),
                op=ast.BitOr(),
                right=ast.Constant(value=None),
            ),
        )
        arg_pickle_control_flow_result = ast.arg(
            arg="pickle_control_flow_result", annotation=ast.Name(id="bool", ctx=ast.Load())
        )
        args = ast.arguments(
            posonlyargs=[],
            args=[arg_input, arg_storage_backend, arg_workflow_executor, arg_pickle_control_flow_result],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[
                ast.Constant(StorageBackend.LOCAL.value),
                ast.Constant(value=None),
                ast.Constant(value=pickle_control_flow_result),
            ],
        )
        #   return annotation: dict | None
        return_annotation = ast.BinOp(
            left=ast.Name(id="dict", ctx=ast.Load()),
            op=ast.BitOr(),
            right=ast.Constant(value=None),
        )

        # Generate the ensure flow context function call
        ensure_context_call = self._generate_ensure_flow_context_call()

        # Convert string storage_backend to StorageBackend enum
        storage_backend_convert = ast.Assign(
            targets=[ast.Name(id="storage_backend_enum", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="StorageBackend", ctx=ast.Load()),
                args=[ast.Name(id="storage_backend", ctx=ast.Load())],
                keywords=[],
            ),
        )

        # Create conditional logic: workflow_executor = workflow_executor or LocalWorkflowExecutor(storage_backend=storage_backend_enum)
        executor_assign = ast.Assign(
            targets=[ast.Name(id="workflow_executor", ctx=ast.Store())],
            value=ast.BoolOp(
                op=ast.Or(),
                values=[
                    ast.Name(id="workflow_executor", ctx=ast.Load()),
                    ast.Call(
                        func=ast.Name(id="LocalWorkflowExecutor", ctx=ast.Load()),
                        args=[],
                        keywords=[
                            ast.keyword(
                                arg="storage_backend", value=ast.Name(id="storage_backend_enum", ctx=ast.Load())
                            ),
                        ],
                    ),
                ],
            ),
        )
        # Use async context manager for workflow execution
        with_stmt = ast.AsyncWith(
            items=[
                ast.withitem(
                    context_expr=ast.Name(id="workflow_executor", ctx=ast.Load()),
                    optional_vars=ast.Name(id="executor", ctx=ast.Store()),
                )
            ],
            body=[
                ast.Expr(
                    value=ast.Await(
                        value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id="executor", ctx=ast.Load()),
                                attr="arun",
                                ctx=ast.Load(),
                            ),
                            args=[],
                            keywords=[
                                ast.keyword(arg="flow_input", value=ast.Name(id="input", ctx=ast.Load())),
                                ast.keyword(
                                    arg="pickle_control_flow_result",
                                    value=ast.Name(id="pickle_control_flow_result", ctx=ast.Load()),
                                ),
                            ],
                        )
                    )
                )
            ],
        )
        return_stmt = ast.Return(
            value=ast.Attribute(
                value=ast.Name(id="executor", ctx=ast.Load()),
                attr="output",
                ctx=ast.Load(),
            )
        )

        # === Generate async aexecute_workflow function ===
        async_func_def = ast.AsyncFunctionDef(
            name="aexecute_workflow",
            args=args,
            body=[ensure_context_call, storage_backend_convert, executor_assign, with_stmt, return_stmt],
            decorator_list=[],
            returns=return_annotation,
            type_params=[],
        )
        ast.fix_missing_locations(async_func_def)

        # === Generate sync execute_workflow function (backward compatibility wrapper) ===
        sync_func_def = ast.FunctionDef(
            name="execute_workflow",
            args=args,
            body=[
                ast.Return(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="asyncio", ctx=ast.Load()),
                            attr="run",
                            ctx=ast.Load(),
                        ),
                        args=[
                            ast.Call(
                                func=ast.Name(id="aexecute_workflow", ctx=ast.Load()),
                                args=[],
                                keywords=[
                                    ast.keyword(arg="input", value=ast.Name(id="input", ctx=ast.Load())),
                                    ast.keyword(
                                        arg="storage_backend", value=ast.Name(id="storage_backend", ctx=ast.Load())
                                    ),
                                    ast.keyword(
                                        arg="workflow_executor", value=ast.Name(id="workflow_executor", ctx=ast.Load())
                                    ),
                                    ast.keyword(
                                        arg="pickle_control_flow_result",
                                        value=ast.Name(id="pickle_control_flow_result", ctx=ast.Load()),
                                    ),
                                ],
                            )
                        ],
                        keywords=[],
                    )
                )
            ],
            decorator_list=[],
            returns=return_annotation,
            type_params=[],
        )
        ast.fix_missing_locations(sync_func_def)

        # === 2) build the `if __name__ == "__main__":` block ===
        main_test = ast.Compare(
            left=ast.Name(id="__name__", ctx=ast.Load()),
            ops=[ast.Eq()],
            comparators=[ast.Constant(value="__main__")],
        )

        parser_assign = ast.Assign(
            targets=[ast.Name(id="parser", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="argparse", ctx=ast.Load()),
                    attr="ArgumentParser",
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            ),
        )

        # Generate parser.add_argument(...) calls for each parameter in workflow_shape
        add_arg_calls = []

        # Add storage backend argument
        add_arg_calls.append(
            ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="parser", ctx=ast.Load()),
                        attr="add_argument",
                        ctx=ast.Load(),
                    ),
                    args=[ast.Constant("--storage-backend")],
                    keywords=[
                        ast.keyword(
                            arg="choices",
                            value=ast.List(
                                elts=[ast.Constant(StorageBackend.LOCAL.value), ast.Constant(StorageBackend.GTC.value)],
                                ctx=ast.Load(),
                            ),
                        ),
                        ast.keyword(arg="default", value=ast.Constant(StorageBackend.LOCAL.value)),
                        ast.keyword(
                            arg="help",
                            value=ast.Constant(
                                "Storage backend to use: 'local' for local filesystem or 'gtc' for Griptape Cloud"
                            ),
                        ),
                    ],
                )
            )
        )

        # Add json input argument
        add_arg_calls.append(
            ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="parser", ctx=ast.Load()),
                        attr="add_argument",
                        ctx=ast.Load(),
                    ),
                    args=[ast.Constant("--json-input")],
                    keywords=[
                        ast.keyword(arg="default", value=ast.Constant(None)),
                        ast.keyword(
                            arg="help",
                            value=ast.Constant(
                                "JSON string containing parameter values. Takes precedence over individual parameter arguments if provided."
                            ),
                        ),
                    ],
                )
            )
        )

        # Generate individual arguments for each parameter in workflow_shape["input"]
        if "input" in workflow_shape:
            for node_name, node_params in workflow_shape["input"].items():
                if isinstance(node_params, dict):
                    for param_name, param_info in node_params.items():
                        # Create CLI argument name: --{param_name}
                        arg_name = f"--{param_name}".lower()

                        # Get help text from parameter info
                        help_text = param_info.get("tooltip", f"Parameter {param_name} for node {node_name}")

                        add_arg_calls.append(
                            ast.Expr(
                                value=ast.Call(
                                    func=ast.Attribute(
                                        value=ast.Name(id="parser", ctx=ast.Load()),
                                        attr="add_argument",
                                        ctx=ast.Load(),
                                    ),
                                    args=[ast.Constant(arg_name)],
                                    keywords=[
                                        ast.keyword(arg="default", value=ast.Constant(None)),
                                        ast.keyword(arg="help", value=ast.Constant(help_text)),
                                    ],
                                )
                            )
                        )

        parse_args = ast.Assign(
            targets=[ast.Name(id="args", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="parser", ctx=ast.Load()),
                    attr="parse_args",
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            ),
        )

        # Build flow_input dictionary from JSON input or individual CLI arguments
        flow_input_init = ast.Assign(
            targets=[ast.Name(id="flow_input", ctx=ast.Store())],
            value=ast.Dict(keys=[], values=[]),
        )

        # Check if json_input is provided and parse it
        json_input_if = ast.If(
            test=ast.Compare(
                left=ast.Attribute(
                    value=ast.Name(id="args", ctx=ast.Load()),
                    attr="json_input",
                    ctx=ast.Load(),
                ),
                ops=[ast.IsNot()],
                comparators=[ast.Constant(value=None)],
            ),
            body=[
                ast.Assign(
                    targets=[ast.Name(id="flow_input", ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="json", ctx=ast.Load()),
                            attr="loads",
                            ctx=ast.Load(),
                        ),
                        args=[
                            ast.Attribute(
                                value=ast.Name(id="args", ctx=ast.Load()),
                                attr="json_input",
                                ctx=ast.Load(),
                            )
                        ],
                        keywords=[],
                    ),
                )
            ],
            orelse=[],
        )

        # Build the flow_input dict structure from individual arguments (fallback when no JSON input)
        build_flow_input_stmts = []

        # For each node, ensure it exists in flow_input
        build_flow_input_stmts.extend(
            [
                ast.If(
                    test=ast.Compare(
                        left=ast.Constant(value=node_name),
                        ops=[ast.NotIn()],
                        comparators=[ast.Name(id="flow_input", ctx=ast.Load())],
                    ),
                    body=[
                        ast.Assign(
                            targets=[
                                ast.Subscript(
                                    value=ast.Name(id="flow_input", ctx=ast.Load()),
                                    slice=ast.Constant(value=node_name),
                                    ctx=ast.Store(),
                                )
                            ],
                            value=ast.Dict(keys=[], values=[]),
                        )
                    ],
                    orelse=[],
                )
                for node_name in workflow_shape.get("input", {})
            ]
        )

        # For each parameter, get its value from args and add to flow_input
        build_flow_input_stmts.extend(
            [
                ast.If(
                    test=ast.Compare(
                        left=ast.Attribute(
                            value=ast.Name(id="args", ctx=ast.Load()),
                            attr=param_name.lower(),
                            ctx=ast.Load(),
                        ),
                        ops=[ast.IsNot()],
                        comparators=[ast.Constant(value=None)],
                    ),
                    body=[
                        ast.Assign(
                            targets=[
                                ast.Subscript(
                                    value=ast.Subscript(
                                        value=ast.Name(id="flow_input", ctx=ast.Load()),
                                        slice=ast.Constant(value=node_name),
                                        ctx=ast.Load(),
                                    ),
                                    slice=ast.Constant(value=param_name),
                                    ctx=ast.Store(),
                                )
                            ],
                            value=ast.Attribute(
                                value=ast.Name(id="args", ctx=ast.Load()),
                                attr=param_name.lower(),
                                ctx=ast.Load(),
                            ),
                        )
                    ],
                    orelse=[],
                )
                for node_name, node_params in workflow_shape.get("input", {}).items()
                if isinstance(node_params, dict)
                for param_name in node_params
            ]
        )

        # Ensure body is not empty - add pass statement if no input parameters
        if not build_flow_input_stmts:
            build_flow_input_stmts = [
                ast.Expr(
                    value=ast.Constant(
                        value="This workflow has no input parameters defined, so there's nothing necessary to supply"
                    )
                ),
                ast.Pass(),
            ]

        # Wrap the individual argument processing in an else clause
        individual_args_else = ast.If(
            test=ast.Compare(
                left=ast.Attribute(
                    value=ast.Name(id="args", ctx=ast.Load()),
                    attr="json_input",
                    ctx=ast.Load(),
                ),
                ops=[ast.Is()],
                comparators=[ast.Constant(value=None)],
            ),
            body=build_flow_input_stmts,
            orelse=[],
        )

        workflow_output = ast.Assign(
            targets=[ast.Name(id="workflow_output", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="execute_workflow", ctx=ast.Load()),
                args=[],
                keywords=[
                    ast.keyword(arg="input", value=ast.Name(id="flow_input", ctx=ast.Load())),
                    ast.keyword(
                        arg="storage_backend",
                        value=ast.Attribute(
                            value=ast.Name(id="args", ctx=ast.Load()),
                            attr="storage_backend",
                            ctx=ast.Load(),
                        ),
                    ),
                ],
            ),
        )
        print_output = ast.Expr(
            value=ast.Call(
                func=ast.Name(id="print", ctx=ast.Load()),
                args=[ast.Name(id="workflow_output", ctx=ast.Load())],
                keywords=[],
            )
        )

        if_node = ast.If(
            test=main_test,
            body=[
                parser_assign,
                *add_arg_calls,
                parse_args,
                flow_input_init,
                json_input_if,
                individual_args_else,
                workflow_output,
                print_output,
            ],
            orelse=[],
        )
        ast.fix_missing_locations(if_node)

        # Generate the ensure flow context function
        ensure_context_func = self._generate_ensure_flow_context_function(import_recorder)

        return [ensure_context_func, sync_func_def, async_func_def, if_node]

    def _generate_ensure_flow_context_function(
        self,
        import_recorder: ImportRecorder,
    ) -> ast.FunctionDef:
        """Generates the _ensure_workflow_context function for the serialized workflow file."""
        import_recorder.add_from_import("griptape_nodes.retained_mode.events.flow_events", "GetTopLevelFlowRequest")
        import_recorder.add_from_import(
            "griptape_nodes.retained_mode.events.flow_events", "GetTopLevelFlowResultSuccess"
        )

        # Function signature: def _ensure_workflow_context():
        func_def = ast.FunctionDef(
            name="_ensure_workflow_context",
            args=ast.arguments(
                posonlyargs=[],
                args=[],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            body=[],
            decorator_list=[],
            returns=None,
            type_params=[],
        )

        context_manager_assign = ast.Assign(
            targets=[ast.Name(id="context_manager", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="GriptapeNodes", ctx=ast.Load()),
                    attr="ContextManager",
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            ),
        )

        # if not context_manager.has_current_flow():
        has_flow_check = ast.UnaryOp(
            op=ast.Not(),
            operand=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="context_manager", ctx=ast.Load()),
                    attr="has_current_flow",
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            ),
        )

        # top_level_flow_request = GetTopLevelFlowRequest()  # noqa: ERA001
        flow_request_assign = ast.Assign(
            targets=[ast.Name(id="top_level_flow_request", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="GetTopLevelFlowRequest", ctx=ast.Load()),
                args=[],
                keywords=[],
            ),
        )

        # top_level_flow_result = GriptapeNodes.handle_request(top_level_flow_request)  # noqa: ERA001
        flow_result_assign = ast.Assign(
            targets=[ast.Name(id="top_level_flow_result", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="GriptapeNodes", ctx=ast.Load()),
                    attr="handle_request",
                    ctx=ast.Load(),
                ),
                args=[ast.Name(id="top_level_flow_request", ctx=ast.Load())],
                keywords=[],
            ),
        )

        # isinstance check and flow_name is not None
        isinstance_check = ast.Call(
            func=ast.Name(id="isinstance", ctx=ast.Load()),
            args=[
                ast.Name(id="top_level_flow_result", ctx=ast.Load()),
                ast.Name(id="GetTopLevelFlowResultSuccess", ctx=ast.Load()),
            ],
            keywords=[],
        )

        flow_name_check = ast.Compare(
            left=ast.Attribute(
                value=ast.Name(id="top_level_flow_result", ctx=ast.Load()),
                attr="flow_name",
                ctx=ast.Load(),
            ),
            ops=[ast.IsNot()],
            comparators=[ast.Constant(value=None)],
        )

        success_condition = ast.BoolOp(
            op=ast.And(),
            values=[isinstance_check, flow_name_check],
        )

        # flow_manager = GriptapeNodes.FlowManager()  # noqa: ERA001
        flow_manager_assign = ast.Assign(
            targets=[ast.Name(id="flow_manager", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="GriptapeNodes", ctx=ast.Load()),
                    attr="FlowManager",
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            ),
        )

        # flow_obj = flow_manager.get_flow_by_name(top_level_flow_result.flow_name)  # noqa: ERA001
        flow_obj_assign = ast.Assign(
            targets=[ast.Name(id="flow_obj", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="flow_manager", ctx=ast.Load()),
                    attr="get_flow_by_name",
                    ctx=ast.Load(),
                ),
                args=[
                    ast.Attribute(
                        value=ast.Name(id="top_level_flow_result", ctx=ast.Load()),
                        attr="flow_name",
                        ctx=ast.Load(),
                    )
                ],
                keywords=[],
            ),
        )

        # context_manager.push_flow(flow_obj)  # noqa: ERA001
        push_flow_call = ast.Expr(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="context_manager", ctx=ast.Load()),
                    attr="push_flow",
                    ctx=ast.Load(),
                ),
                args=[ast.Name(id="flow_obj", ctx=ast.Load())],
                keywords=[],
            ),
        )

        # Build the inner if statement for success condition
        success_if = ast.If(
            test=success_condition,
            body=[
                flow_manager_assign,
                flow_obj_assign,
                push_flow_call,
            ],
            orelse=[],
        )

        # Build the main if statement
        main_if = ast.If(
            test=has_flow_check,
            body=[
                flow_request_assign,
                flow_result_assign,
                success_if,
            ],
            orelse=[],
        )

        # Set the function body
        func_def.body = [context_manager_assign, main_if]
        ast.fix_missing_locations(func_def)

        return func_def

    def _generate_ensure_flow_context_call(
        self,
    ) -> ast.Expr:
        """Generates the call to _ensure_workflow_context() function."""
        return ast.Expr(
            value=ast.Call(
                func=ast.Name(id="_ensure_workflow_context", ctx=ast.Load()),
                args=[],
                keywords=[],
            )
        )

    def _generate_workflow_run_prerequisite_code(
        self,
        workflow_name: str,
        import_recorder: ImportRecorder,
    ) -> list[ast.AST]:
        import_recorder.add_from_import("griptape_nodes.retained_mode.events.library_events", "LoadLibrariesRequest")

        code_blocks: list[ast.AST] = []

        # Generate load libraries request call
        # TODO (https://github.com/griptape-ai/griptape-nodes/issues/1615): Generate requests to load ONLY the libraries used in this workflow
        load_call = ast.Expr(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="GriptapeNodes", ctx=ast.Load()),
                    attr="handle_request",
                    ctx=ast.Load(),
                ),
                args=[
                    ast.Call(
                        func=ast.Name(id="LoadLibrariesRequest", ctx=ast.Load()),
                        args=[],
                        keywords=[],
                    )
                ],
                keywords=[],
            )
        )
        ast.fix_missing_locations(load_call)
        code_blocks.append(load_call)

        # Generate context manager assignment
        assign_context_manager = ast.Assign(
            targets=[ast.Name(id="context_manager", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="GriptapeNodes", ctx=ast.Load()),
                    attr="ContextManager",
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            ),
        )
        ast.fix_missing_locations(assign_context_manager)
        code_blocks.append(assign_context_manager)

        has_check = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="context_manager", ctx=ast.Load()),
                attr="has_current_workflow",
                ctx=ast.Load(),
            ),
            args=[],
            keywords=[],
        )
        test = ast.UnaryOp(op=ast.Not(), operand=has_check)

        push_call = ast.Expr(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="context_manager", ctx=ast.Load()),
                    attr="push_workflow",
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[ast.keyword(arg="workflow_name", value=ast.Constant(value=workflow_name))],
            )
        )
        ast.fix_missing_locations(push_call)

        if_stmt = ast.If(
            test=test,
            body=[push_call],
            orelse=[],
        )
        ast.fix_missing_locations(if_stmt)
        code_blocks.append(if_stmt)
        return code_blocks

    def _generate_unique_values_code(
        self,
        unique_parameter_uuid_to_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any],
        prefix: str,
        import_recorder: ImportRecorder,
    ) -> ast.AST:
        if len(unique_parameter_uuid_to_values) == 0:
            return ast.Module(body=[], type_ignores=[])

        import_recorder.add_import("pickle")

        # Get the list of manually-curated, globally available modules
        global_modules_set = {"builtins", "__main__"}

        # Serialize the unique values as pickled strings.
        # IMPORTANT: We patch dynamic module names to stable namespaces before pickling
        # to ensure generated workflows can reliably import the required classes.
        unique_parameter_dict = {}

        for uuid, unique_parameter_value in unique_parameter_uuid_to_values.items():
            # Dynamic Module Patching Strategy:
            # When we pickle objects from dynamically loaded modules (like VideoUrlArtifact),
            # pickle stores the class's __module__ attribute in the binary data. If we don't
            # patch this, the pickle data would contain something like:
            #   "gtn_dynamic_module_image_to_video_py_123456789.VideoUrlArtifact"
            #
            # When the workflow runs later, Python tries to import this module name, which
            # fails because dynamic modules don't exist in fresh Python processes.
            #
            # Our solution: Temporarily patch the class's __module__ to use the stable namespace
            # before pickling, so the pickle data contains:
            #   "griptape_nodes.node_libraries.runwayml_library.image_to_video.VideoUrlArtifact"
            #
            # This includes recursive patching for nested objects in containers (lists, tuples, dicts)

            # Apply recursive dynamic module patching, pickle, then restore
            unique_parameter_bytes = self._patch_and_pickle_object(unique_parameter_value)

            # Encode the bytes as a string using latin1
            unique_parameter_byte_str = unique_parameter_bytes.decode("latin1")
            unique_parameter_dict[uuid] = unique_parameter_byte_str

            # Collect import statements for all classes in the object tree
            self._collect_object_imports(unique_parameter_value, import_recorder, global_modules_set)

        # Generate a comment explaining what we're doing:
        comment_text = (
            "\n"
            "1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.\n"
            "   This minimizes the size of the code, especially for large objects like serialized image files.\n"
            "2. We're using a prefix so that it's clear which Flow these values are associated with.\n"
            "3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes\n"
            "   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise\n"
            "   would be difficult to serialize.\n"
        )

        # Generate the dictionary of unique values
        unique_values_dict_name = f"{prefix}_unique_values_dict"
        unique_values_ast = ast.Assign(
            targets=[ast.Name(id=unique_values_dict_name, ctx=ast.Store(), lineno=1, col_offset=0)],
            value=ast.Dict(
                keys=[ast.Constant(value=str(uuid), lineno=1, col_offset=0) for uuid in unique_parameter_dict],
                values=[
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
                    for byte_str in unique_parameter_dict.values()
                ],
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

    def _generate_create_flow(
        self, create_flow_command: CreateFlowRequest, import_recorder: ImportRecorder, flow_creation_index: int
    ) -> ast.Module:
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

        # Create a comment explaining the behavior
        comment_ast = ast.Expr(
            value=ast.Constant(
                value="# Create the Flow, then do work within it as context.",
                lineno=1,
                col_offset=0,
            ),
            lineno=1,
            col_offset=0,
        )

        # Construct the AST for creating the flow
        flow_variable_name = f"flow{flow_creation_index}_name"
        create_flow_result = ast.Assign(
            targets=[ast.Name(id=flow_variable_name, ctx=ast.Store(), lineno=1, col_offset=0)],
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
                attr="flow_name",
                ctx=ast.Load(),
                lineno=1,
                col_offset=0,
            ),
            lineno=1,
            col_offset=0,
        )

        # Return both the comment and the assignment as a module
        return ast.Module(body=[comment_ast, create_flow_result], type_ignores=[])

    def _generate_import_workflow(
        self,
        import_workflow_command: ImportWorkflowAsReferencedSubFlowRequest,
        import_recorder: ImportRecorder,
        flow_creation_index: int,
    ) -> ast.Module:
        """Generate AST code for importing a referenced workflow.

        Creates an assignment statement that executes an ImportWorkflowAsReferencedSubFlowRequest
        and stores the resulting flow name in a variable.

        Args:
            import_workflow_command: The import request containing the workflow file path
            import_recorder: Tracks imports needed for the generated code
            flow_creation_index: Index used to generate unique variable names

        Returns:
            AST assignment node representing the import workflow command

        Example output:
            flow1_name = GriptapeNodes.handle_request(ImportWorkflowAsReferencedSubFlowRequest(
                file_path='/path/to/workflow.py'
            )).created_flow_name
        """
        import_recorder.add_from_import(
            "griptape_nodes.retained_mode.events.workflow_events", "ImportWorkflowAsReferencedSubFlowRequest"
        )

        # Prepare arguments for ImportWorkflowAsReferencedSubFlowRequest
        import_workflow_request_args = []

        # Omit values that match default values.
        if is_dataclass(import_workflow_command):
            for field in fields(import_workflow_command):
                field_value = getattr(import_workflow_command, field.name)
                if field_value != field.default:
                    import_workflow_request_args.append(
                        ast.keyword(arg=field.name, value=ast.Constant(value=field_value, lineno=1, col_offset=0))
                    )

        # Construct the AST for importing the workflow
        flow_variable_name = f"flow{flow_creation_index}_name"
        import_workflow_result = ast.Assign(
            targets=[ast.Name(id=flow_variable_name, ctx=ast.Store(), lineno=1, col_offset=0)],
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
                            func=ast.Name(
                                id="ImportWorkflowAsReferencedSubFlowRequest", ctx=ast.Load(), lineno=1, col_offset=0
                            ),
                            args=[],
                            keywords=import_workflow_request_args,
                            lineno=1,
                            col_offset=0,
                        )
                    ],
                    keywords=[],
                    lineno=1,
                    col_offset=0,
                ),
                attr="created_flow_name",
                ctx=ast.Load(),
                lineno=1,
                col_offset=0,
            ),
            lineno=1,
            col_offset=0,
        )

        return ast.Module(body=[import_workflow_result], type_ignores=[])

    def _generate_assign_flow_context(
        self,
        flow_initialization_command: CreateFlowRequest | ImportWorkflowAsReferencedSubFlowRequest | None,
        flow_creation_index: int,
    ) -> ast.With:
        context_manager = ast.Attribute(
            value=ast.Name(id="GriptapeNodes", ctx=ast.Load(), lineno=1, col_offset=0),
            attr="ContextManager",
            ctx=ast.Load(),
            lineno=1,
            col_offset=0,
        )

        if flow_initialization_command is None:
            # Construct AST for "GriptapeNodes.ContextManager().flow(GriptapeNodes.ContextManager().get_current_flow().flow_name)"
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
                        value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Call(func=context_manager, args=[], keywords=[], lineno=1, col_offset=0),
                                attr="get_current_flow",
                                ctx=ast.Load(),
                                lineno=1,
                                col_offset=0,
                            ),
                            args=[],
                            keywords=[],
                            lineno=1,
                            col_offset=0,
                        ),
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
        else:
            # Construct AST for "GriptapeNodes.ContextManager().flow(flow{flow_creation_index}_name)"
            flow_variable_name = f"flow{flow_creation_index}_name"
            flow_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Call(func=context_manager, args=[], keywords=[], lineno=1, col_offset=0),
                    attr="flow",
                    ctx=ast.Load(),
                    lineno=1,
                    col_offset=0,
                ),
                args=[ast.Name(id=flow_variable_name, ctx=ast.Load(), lineno=1, col_offset=0)],
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

    def _generate_nodes_in_flow(
        self,
        serialized_flow_commands: SerializedFlowCommands,
        import_recorder: ImportRecorder,
        node_uuid_to_node_variable_name: dict[SerializedNodeCommands.NodeUUID, str],
    ) -> list[ast.stmt]:
        # Generate node creation code and add it to the flow context
        node_creation_asts = []
        for node_index, serialized_node_command in enumerate(serialized_flow_commands.serialized_node_commands):
            node_creation_ast = self._generate_node_creation_code(
                serialized_node_command,
                node_index,
                import_recorder,
                node_uuid_to_node_variable_name=node_uuid_to_node_variable_name,
            )
            node_creation_asts.extend(node_creation_ast)
        return node_creation_asts

    def _generate_node_creation_code(
        self,
        serialized_node_command: SerializedNodeCommands,
        node_index: int,
        import_recorder: ImportRecorder,
        node_uuid_to_node_variable_name: dict[SerializedNodeCommands.NodeUUID, str],
    ) -> list[ast.stmt]:
        # Ensure necessary imports are recorded
        import_recorder.add_from_import("griptape_nodes.node_library.library_registry", "NodeMetadata")
        import_recorder.add_from_import("griptape_nodes.node_library.library_registry", "NodeDeprecationMetadata")
        import_recorder.add_from_import("griptape_nodes.node_library.library_registry", "IconVariant")
        import_recorder.add_from_import("griptape_nodes.retained_mode.events.node_events", "CreateNodeRequest")
        import_recorder.add_from_import(
            "griptape_nodes.retained_mode.events.parameter_events", "AddParameterToNodeRequest"
        )
        import_recorder.add_from_import(
            "griptape_nodes.retained_mode.events.parameter_events", "AlterParameterDetailsRequest"
        )

        # Generate the VARIABLE name that codegen will use for this node.
        node_variable_name = f"node{node_index}_name"

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
            targets=[ast.Name(id=node_variable_name, ctx=ast.Store(), lineno=1, col_offset=0)],
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

        # Populate the dictionary with the node VARIABLE name and the node's UUID.
        node_uuid_to_node_variable_name[serialized_node_command.node_uuid] = node_variable_name

        return node_creation_ast

    def _generate_connections_code(
        self,
        serialized_connections: list[SerializedFlowCommands.IndirectConnectionSerialization],
        node_uuid_to_node_variable_name: dict[SerializedNodeCommands.NodeUUID, str],
        import_recorder: ImportRecorder,
    ) -> list[ast.stmt]:
        # Ensure necessary imports are recorded
        import_recorder.add_from_import(
            "griptape_nodes.retained_mode.events.connection_events", "CreateConnectionRequest"
        )

        connection_asts = []

        for connection in serialized_connections:
            # Match the connection's node UUID back to its variable name.
            source_node_variable_name = node_uuid_to_node_variable_name[connection.source_node_uuid]
            target_node_variable_name = node_uuid_to_node_variable_name[connection.target_node_uuid]

            create_connection_request_args = [
                ast.keyword(
                    arg="source_node_name",
                    value=ast.Name(id=source_node_variable_name, ctx=ast.Load()),
                ),
                ast.keyword(arg="source_parameter_name", value=ast.Constant(value=connection.source_parameter_name)),
                ast.keyword(
                    arg="target_node_name",
                    value=ast.Name(id=target_node_variable_name, ctx=ast.Load()),
                ),
                ast.keyword(arg="target_parameter_name", value=ast.Constant(value=connection.target_parameter_name)),
                ast.keyword(arg="initial_setup", value=ast.Constant(value=True)),
            ]

            create_connection_call = ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="GriptapeNodes", ctx=ast.Load()), attr="handle_request", ctx=ast.Load()
                    ),
                    args=[
                        ast.Call(
                            func=ast.Name(id="CreateConnectionRequest", ctx=ast.Load()),
                            args=[],
                            keywords=create_connection_request_args,
                        )
                    ],
                    keywords=[],
                )
            )

            connection_asts.append(create_connection_call)

        return connection_asts

    def _generate_set_parameter_value_code(
        self,
        set_parameter_value_commands: dict[
            SerializedNodeCommands.NodeUUID, list[SerializedNodeCommands.IndirectSetParameterValueCommand]
        ],
        lock_commands: dict[SerializedNodeCommands.NodeUUID, SetLockNodeStateRequest],
        node_uuid_to_node_variable_name: dict[SerializedNodeCommands.NodeUUID, str],
        unique_values_dict_name: str,
        import_recorder: ImportRecorder,
    ) -> list[ast.stmt]:
        parameter_value_asts = []
        for node_uuid, indirect_set_parameter_value_commands in set_parameter_value_commands.items():
            node_variable_name = node_uuid_to_node_variable_name[node_uuid]
            lock_node_command = lock_commands.get(node_uuid)
            parameter_value_asts.extend(
                self._generate_set_parameter_value_for_node(
                    node_variable_name,
                    indirect_set_parameter_value_commands,
                    unique_values_dict_name,
                    import_recorder,
                    lock_node_command,
                )
            )
        return parameter_value_asts

    def _generate_set_parameter_value_for_node(
        self,
        node_variable_name: str,
        indirect_set_parameter_value_commands: list[SerializedNodeCommands.IndirectSetParameterValueCommand],
        unique_values_dict_name: str,
        import_recorder: ImportRecorder,
        lock_node_command: SetLockNodeStateRequest | None = None,
    ) -> list[ast.stmt]:
        if not indirect_set_parameter_value_commands and lock_node_command is None:
            return []

        if indirect_set_parameter_value_commands:
            import_recorder.add_from_import(
                "griptape_nodes.retained_mode.events.parameter_events", "SetParameterValueRequest"
            )

        set_parameter_value_asts = []
        with_node_context = ast.With(
            items=[
                ast.withitem(
                    context_expr=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="GriptapeNodes", ctx=ast.Load(), lineno=1, col_offset=0),
                            attr="ContextManager().node",
                            ctx=ast.Load(),
                            lineno=1,
                            col_offset=0,
                        ),
                        args=[ast.Name(id=node_variable_name, ctx=ast.Load(), lineno=1, col_offset=0)],
                        keywords=[],
                        lineno=1,
                        col_offset=0,
                    ),
                    optional_vars=None,
                )
            ],
            body=[],
            lineno=1,
            col_offset=0,
        )

        for command in indirect_set_parameter_value_commands:
            value_lookup = ast.Subscript(
                value=ast.Name(id=unique_values_dict_name, ctx=ast.Load(), lineno=1, col_offset=0),
                slice=ast.Constant(value=str(command.unique_value_uuid), lineno=1, col_offset=0),
                ctx=ast.Load(),
                lineno=1,
                col_offset=0,
            )

            set_parameter_value_request_call = ast.Expr(
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
                            func=ast.Name(id="SetParameterValueRequest", ctx=ast.Load(), lineno=1, col_offset=0),
                            args=[],
                            keywords=[
                                ast.keyword(
                                    arg="parameter_name",
                                    value=ast.Constant(
                                        value=command.set_parameter_value_command.parameter_name, lineno=1, col_offset=0
                                    ),
                                ),
                                ast.keyword(
                                    arg="node_name",
                                    value=ast.Name(id=node_variable_name, ctx=ast.Load(), lineno=1, col_offset=0),
                                ),
                                ast.keyword(arg="value", value=value_lookup, lineno=1, col_offset=0),
                                ast.keyword(
                                    arg="initial_setup", value=ast.Constant(value=True, lineno=1, col_offset=0)
                                ),
                                ast.keyword(
                                    arg="is_output",
                                    value=ast.Constant(
                                        value=command.set_parameter_value_command.is_output, lineno=1, col_offset=0
                                    ),
                                ),
                            ],
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
            with_node_context.body.append(set_parameter_value_request_call)

        # Add lock command as the LAST command in the with context
        if lock_node_command is not None:
            import_recorder.add_from_import(
                "griptape_nodes.retained_mode.events.node_events", "SetLockNodeStateRequest"
            )

            lock_node_call_ast = ast.Expr(
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
                            func=ast.Name(id="SetLockNodeStateRequest", ctx=ast.Load(), lineno=1, col_offset=0),
                            args=[],
                            keywords=[
                                ast.keyword(arg="node_name", value=ast.Constant(value=None, lineno=1, col_offset=0)),
                                ast.keyword(
                                    arg="lock", value=ast.Constant(value=lock_node_command.lock, lineno=1, col_offset=0)
                                ),
                            ],
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
            with_node_context.body.append(lock_node_call_ast)

        set_parameter_value_asts.append(with_node_context)
        return set_parameter_value_asts

    @classmethod
    def _convert_parameter_to_minimal_dict(cls, parameter: Parameter) -> dict[str, Any]:
        """Converts a parameter to a minimal dictionary for loading up a dynamic, black-box Node."""
        param_dict = parameter.to_dict()
        fields_to_include = [
            "name",
            "tooltip",
            "type",
            "input_types",
            "output_type",
            "default_value",
            "tooltip_as_input",
            "tooltip_as_property",
            "tooltip_as_output",
            "allowed_modes",
            "converters",
            "validators",
            "traits",
            "ui_options",
            "settable",
            "is_user_defined",
            "parent_container_name",
            "parent_element_name",
        ]
        minimal_dict = {key: param_dict[key] for key in fields_to_include if key in param_dict}
        minimal_dict["settable"] = bool(getattr(parameter, "settable", True))
        minimal_dict["is_user_defined"] = bool(getattr(param_dict, "is_user_defined", True))

        return minimal_dict

    def _create_workflow_shape_from_nodes(
        self,
        nodes: Sequence[BaseNode],
        workflow_shape: dict[str, Any],
        workflow_shape_type: str,
    ) -> dict[str, Any]:
        """Creates a workflow shape from the nodes.

        This method iterates over a sequence of a certain Node type (input or output)
        and creates a dictionary representation of the workflow shape. This informs which
        Parameters can be set for input, and which Parameters are expected as output.
        """
        for node in nodes:
            for param in node.parameters:
                # Expose only the parameters that are relevant for workflow input and output.
                param_info = self.extract_parameter_shape_info(param, include_control_params=True)
                if param_info is not None:
                    if node.name in workflow_shape[workflow_shape_type]:
                        cast("dict", workflow_shape[workflow_shape_type][node.name])[param.name] = param_info
                    else:
                        workflow_shape[workflow_shape_type][node.name] = {param.name: param_info}
        return workflow_shape

    def extract_workflow_shape(self, workflow_name: str) -> dict[str, Any]:
        """Extracts the input and output shape for a workflow.

        Here we gather information about the Workflow's exposed input and output Parameters
        such that a client invoking the Workflow can understand what values to provide
        as well as what values to expect back as output.
        """
        workflow_shape: dict[str, Any] = {"input": {}, "output": {}}

        flow_manager = GriptapeNodes.FlowManager()
        result = flow_manager.on_get_top_level_flow_request(GetTopLevelFlowRequest())
        if result.failed():
            details = f"Workflow '{workflow_name}' does not have a top-level flow."
            raise ValueError(details)
        flow_name = cast("GetTopLevelFlowResultSuccess", result).flow_name
        if flow_name is None:
            details = f"Workflow '{workflow_name}' does not have a top-level flow."
            raise ValueError(details)

        control_flow = flow_manager.get_flow_by_name(flow_name)
        nodes = control_flow.nodes

        start_nodes: list[StartNode] = []
        end_nodes: list[EndNode] = []

        # First, validate that there are at least one StartNode and one EndNode
        for node in nodes.values():
            if isinstance(node, StartNode):
                start_nodes.append(node)
            elif isinstance(node, EndNode):
                end_nodes.append(node)
        if len(start_nodes) < 1:
            details = f"Workflow '{workflow_name}' does not have a StartNode."
            raise ValueError(details)
        if len(end_nodes) < 1:
            details = f"Workflow '{workflow_name}' does not have an EndNode."
            raise ValueError(details)

        # Now, we need to gather the input and output parameters for each node type.
        workflow_shape = self._create_workflow_shape_from_nodes(
            nodes=start_nodes,
            workflow_shape=workflow_shape,
            workflow_shape_type="input",
        )
        workflow_shape = self._create_workflow_shape_from_nodes(
            nodes=end_nodes,
            workflow_shape=workflow_shape,
            workflow_shape_type="output",
        )

        return workflow_shape

    def extract_parameter_shape_info(
        self, parameter: Parameter, *, include_control_params: bool
    ) -> ParameterShapeInfo | None:
        """Extract shape information from a parameter for workflow shape building.

        Expose only the parameters that are relevant for workflow input and output.

        Args:
            parameter: The parameter to extract shape info from
            include_control_params: Whether to include control type parameters (default: False)

        Returns:
            Parameter info dict if relevant for workflow shape, None if should be excluded
        """
        # Conditionally exclude control types
        if not include_control_params and parameter.type == ParameterTypeBuiltin.CONTROL_TYPE.value:
            return None

        return self._convert_parameter_to_minimal_dict(parameter)

    def build_workflow_shape_from_parameter_info(
        self, input_node_params: WorkflowShapeNodes, output_node_params: WorkflowShapeNodes
    ) -> WorkflowShape:
        """Build a WorkflowShape from collected parameter information.

        Args:
            input_node_params: Mapping of input node names to their parameter info
            output_node_params: Mapping of output node names to their parameter info

        Returns:
            WorkflowShape object with inputs and outputs
        """
        return WorkflowShape(inputs=input_node_params, outputs=output_node_params)

    async def on_publish_workflow_request(self, request: PublishWorkflowRequest) -> ResultPayload:
        try:
            publisher_name = request.publisher_name
            event_handler_mappings = GriptapeNodes.LibraryManager().get_registered_event_handlers(
                request_type=type(request)
            )
            publishing_handler = event_handler_mappings.get(publisher_name)

            if publishing_handler is None:
                msg = f"No publishing handler found for '{publisher_name}' in request type '{type(request).__name__}'."
                raise ValueError(msg)  # noqa: TRY301

            # Save the workflow before publishing to ensure the latest changes in memory are included
            workflow_file_name = request.workflow_name
            try:
                workflow = WorkflowRegistry.get_workflow_by_name(request.workflow_name)
                workflow_file_name = Path(workflow.file_path).stem
            except KeyError:
                details = (
                    f"While publishing, workflow '{request.workflow_name}' had not been saved or could not be found in the Workflow Registry. "
                    "Saving as a new and registered workflow before proceeding on publish attempt."
                )
                logger.info(details)
            await GriptapeNodes.ahandle_request(SaveWorkflowRequest(file_name=workflow_file_name))

            result = await asyncio.to_thread(publishing_handler.handler, request)
            if isinstance(result, PublishWorkflowResultSuccess):
                workflow_file = Path(result.published_workflow_file_path)
                result = self._register_published_workflow_file(workflow_file, result)

            return result  # noqa: TRY300
        except Exception as e:
            details = f"Failed to publish workflow '{request.workflow_name}': {e!s}"
            logger.exception(details)
            return PublishWorkflowResultFailure(exception=e, result_details=details)

    def _register_published_workflow_file(
        self, workflow_file: Path, result: PublishWorkflowResultSuccess
    ) -> ResultPayload:
        """Register a published workflow file in the workflow registry."""
        result_messages: list[ResultDetail] = []

        final_result: ResultPayload = result
        if isinstance(result.result_details, ResultDetails):
            result_messages.extend(result.result_details.result_details)
        else:
            result_messages.append(ResultDetail(message=result.result_details, level=logging.INFO))

        if workflow_file.exists() and workflow_file.is_file():
            load_workflow_metadata_request = LoadWorkflowMetadata(
                file_name=workflow_file.name,
            )
            load_metadata_result = self.on_load_workflow_metadata_request(load_workflow_metadata_request)
            if isinstance(load_metadata_result, LoadWorkflowMetadataResultSuccess):
                try:
                    _workflow = WorkflowRegistry.get_workflow_by_name(load_metadata_result.metadata.name)
                    # This workflow was registered previously, but now it's been updated (potentially including the metadata), so let's re-register
                    WorkflowRegistry.delete_workflow_by_name(load_metadata_result.metadata.name)
                except KeyError:
                    pass

                register_workflow_result = self.on_register_workflow_request(
                    RegisterWorkflowRequest(
                        metadata=load_metadata_result.metadata,
                        file_name=workflow_file.name,
                    )
                )
                if isinstance(register_workflow_result, RegisterWorkflowResultSuccess):
                    success_message = f"Successfully registered new workflow with file '{workflow_file.name}'."
                    result_messages.append(ResultDetail(message=success_message, level=logging.INFO))
                    final_result.result_details = ResultDetails(*result_messages)
                else:
                    exception = cast("RegisterWorkflowResultFailure", register_workflow_result).exception
                    failure_message = f"Failed to register workflow with file '{workflow_file.name}': {exception}"
                    result_messages.append(ResultDetail(message=failure_message, level=logging.ERROR))
                    final_result = PublishWorkflowResultFailure(
                        result_details=ResultDetails(*result_messages), exception=exception
                    )
            else:
                metadata_failure_message = (
                    f"Failed to load metadata for workflow file '{workflow_file.name}'. Not registering workflow."
                )
                result_messages = [ResultDetail(message=metadata_failure_message, level=logging.ERROR)]
                final_result = PublishWorkflowResultFailure(result_details=ResultDetails(*result_messages))

        else:
            result_messages.append(
                ResultDetail(message=f"Workflow file '{workflow_file.name}' does not exist.", level=logging.ERROR)
            )
            final_result = PublishWorkflowResultFailure(result_details=ResultDetails(*result_messages))

        return final_result

    async def on_import_workflow_as_referenced_sub_flow_request(
        self, request: ImportWorkflowAsReferencedSubFlowRequest
    ) -> ResultPayload:
        """Import a registered workflow as a new referenced sub flow in the current context."""
        # Validate prerequisites
        validation_error = self._validate_import_prerequisites(request)
        if validation_error:
            return validation_error

        # Get the workflow (validation passed, so we know it exists)
        workflow = self._get_workflow_by_name(request.workflow_name)

        # Determine target flow name
        if request.flow_name is not None:
            flow_name = request.flow_name
        else:
            flow_name = GriptapeNodes.ContextManager().get_current_flow().name

        # Execute the import
        return await self._execute_workflow_import(request, workflow, flow_name)

    def _validate_import_prerequisites(self, request: ImportWorkflowAsReferencedSubFlowRequest) -> ResultPayload | None:
        """Validate all prerequisites for import. Returns error result or None if valid."""
        # Check workflow exists and get it
        try:
            workflow = self._get_workflow_by_name(request.workflow_name)
        except KeyError:
            details = f"Attempted to import workflow '{request.workflow_name}' as referenced sub flow. Failed because workflow is not registered"
            return ImportWorkflowAsReferencedSubFlowResultFailure(result_details=details)

        # Check workflow version - Schema version 0.6.0+ required for referenced workflow imports
        # (workflow schema was fixed in 0.6.0 to support importing workflows)
        required_version = semver.VersionInfo(major=0, minor=6, patch=0)
        try:
            workflow_version = semver.VersionInfo.parse(workflow.metadata.schema_version)
        except Exception as e:
            details = f"Attempted to import workflow '{request.workflow_name}' as referenced sub flow. Failed because workflow version '{workflow.metadata.schema_version}' caused an error: {e}"
            return ImportWorkflowAsReferencedSubFlowResultFailure(result_details=details)
        if workflow_version < required_version:
            details = f"Attempted to import workflow '{request.workflow_name}' as referenced sub flow. Failed because workflow version '{workflow.metadata.schema_version}' is less than required version '0.6.0'. To remedy, open the workflow you are attempting to import and save it again to upgrade it to the latest version."
            return ImportWorkflowAsReferencedSubFlowResultFailure(result_details=details)

        # Check target flow
        flow_name = request.flow_name
        if flow_name is None:
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = f"Attempted to import workflow '{request.workflow_name}' into Current Context. Failed because Current Context was empty"
                return ImportWorkflowAsReferencedSubFlowResultFailure(result_details=details)
        else:
            # Validate that the specified flow exists
            flow_manager = GriptapeNodes.FlowManager()
            try:
                flow_manager.get_flow_by_name(flow_name)
            except KeyError:
                details = f"Attempted to import workflow '{request.workflow_name}' into flow '{flow_name}'. Failed because target flow does not exist"
                return ImportWorkflowAsReferencedSubFlowResultFailure(result_details=details)

        return None

    def _get_workflow_by_name(self, workflow_name: str) -> Workflow:
        """Get workflow by name from the registry."""
        return WorkflowRegistry.get_workflow_by_name(workflow_name)

    async def _execute_workflow_import(
        self, request: ImportWorkflowAsReferencedSubFlowRequest, workflow: Workflow, flow_name: str
    ) -> ResultPayload:
        """Execute the actual workflow import."""
        # Get current flows before importing
        obj_manager = GriptapeNodes.ObjectManager()
        flows_before = set(obj_manager.get_filtered_subset(type=ControlFlow).keys())

        # Execute the workflow within the target flow context and referenced context
        with GriptapeNodes.ContextManager().flow(flow_name):  # noqa: SIM117
            with self.ReferencedWorkflowContext(self, request.workflow_name):
                workflow_result = await self.run_workflow(workflow.file_path)

        if not workflow_result.execution_successful:
            details = f"Attempted to import workflow '{request.workflow_name}' as referenced sub flow. Failed because workflow execution failed: {workflow_result.execution_details}"
            return ImportWorkflowAsReferencedSubFlowResultFailure(result_details=details)

        # Get flows after importing to find the new referenced sub flow
        flows_after = set(obj_manager.get_filtered_subset(type=ControlFlow).keys())
        new_flows = flows_after - flows_before

        if not new_flows:
            details = f"Attempted to import workflow '{request.workflow_name}' as referenced sub flow. Failed because no new flow was created"
            return ImportWorkflowAsReferencedSubFlowResultFailure(result_details=details)

        # For now, use the first created flow as the main imported flow
        # This handles nested workflows correctly since sub-flows are expected
        created_flow_name = next(iter(new_flows))

        if len(new_flows) > 1:
            logger.debug(
                "Multiple flows created during import of '%s'. Main flow: %s, Sub-flows: %s",
                request.workflow_name,
                created_flow_name,
                [flow for flow in new_flows if flow != created_flow_name],
            )

        # Apply imported flow metadata if provided
        if request.imported_flow_metadata:
            set_metadata_request = SetFlowMetadataRequest(
                flow_name=created_flow_name, metadata=request.imported_flow_metadata
            )
            set_metadata_result = GriptapeNodes.handle_request(set_metadata_request)

            if not isinstance(set_metadata_result, SetFlowMetadataResultSuccess):
                details = f"Attempted to import workflow '{request.workflow_name}' as referenced sub flow. Failed because metadata could not be applied to created flow '{created_flow_name}'"
                return ImportWorkflowAsReferencedSubFlowResultFailure(result_details=details)

            logger.debug(
                "Applied imported flow metadata to '%s': %s", created_flow_name, request.imported_flow_metadata
            )

        details = (
            f"Successfully imported workflow '{request.workflow_name}' as referenced sub flow '{created_flow_name}'"
        )
        return ImportWorkflowAsReferencedSubFlowResultSuccess(
            created_flow_name=created_flow_name, result_details=details
        )

    def on_branch_workflow_request(self, request: BranchWorkflowRequest) -> ResultPayload:
        """Create a branch (copy) of an existing workflow with branch tracking."""
        try:
            # Validate source workflow exists
            source_workflow = WorkflowRegistry.get_workflow_by_name(request.workflow_name)
        except KeyError:
            details = f"Failed to branch workflow '{request.workflow_name}' because it does not exist"
            return BranchWorkflowResultFailure(result_details=details)

        # Generate branch name if not provided
        branch_name = request.branched_workflow_name
        if branch_name is None:
            base_name = request.workflow_name
            counter = 1
            branch_name = f"{base_name}_branch_{counter}"
            while WorkflowRegistry.has_workflow_with_name(branch_name):
                counter += 1
                branch_name = f"{base_name}_branch_{counter}"

        # Check if branch name already exists
        if WorkflowRegistry.has_workflow_with_name(branch_name):
            details = f"Failed to branch workflow '{request.workflow_name}' because branch name '{branch_name}' already exists"
            return BranchWorkflowResultFailure(result_details=details)

        try:
            # Create branch metadata by copying source metadata
            branch_metadata = WorkflowMetadata(
                name=branch_name,
                schema_version=source_workflow.metadata.schema_version,
                engine_version_created_with=source_workflow.metadata.engine_version_created_with,
                node_libraries_referenced=source_workflow.metadata.node_libraries_referenced.copy(),
                node_types_used=source_workflow.metadata.node_types_used.copy(),
                workflows_referenced=source_workflow.metadata.workflows_referenced.copy()
                if source_workflow.metadata.workflows_referenced
                else None,
                description=source_workflow.metadata.description,
                image=source_workflow.metadata.image,
                is_griptape_provided=False,  # Branches are always user-created
                is_template=False,
                creation_date=datetime.now(tz=UTC),
                last_modified_date=source_workflow.metadata.last_modified_date,
                branched_from=request.workflow_name,
            )

            # Prepare branch file path
            branch_file_path = f"{branch_name}.py"

            # Read source workflow content and replace metadata header
            source_file_path = WorkflowRegistry.get_complete_file_path(source_workflow.file_path)
            if not Path(source_file_path).exists():
                details = f"Failed to branch workflow '{request.workflow_name}': File path '{source_file_path}' does not exist. The workflow may have been moved or the workspace configuration may have changed."
                return BranchWorkflowResultFailure(result_details=details)

            source_content = Path(source_file_path).read_text(encoding="utf-8")

            # Replace the metadata header with branch metadata
            branch_content = self._replace_workflow_metadata_header(source_content, branch_metadata)
            if branch_content is None:
                details = f"Failed to replace metadata header for branch workflow '{branch_name}'"
                return BranchWorkflowResultFailure(result_details=details)

            # Write branch workflow file to disk BEFORE registering in registry
            branch_full_path = WorkflowRegistry.get_complete_file_path(branch_file_path)
            Path(branch_full_path).write_text(branch_content, encoding="utf-8")

            # Now create the branch workflow in registry (file must exist on disk first)
            WorkflowRegistry.generate_new_workflow(metadata=branch_metadata, file_path=branch_file_path)

            # Register the branch in user configuration
            config_manager = GriptapeNodes.ConfigManager()
            config_manager.save_user_workflow_json(branch_full_path)

            details = f"Successfully branched workflow '{request.workflow_name}' as '{branch_name}'"
            return BranchWorkflowResultSuccess(
                branched_workflow_name=branch_name,
                original_workflow_name=request.workflow_name,
                result_details=ResultDetails(message=details, level=logging.INFO),
            )

        except Exception as e:
            details = f"Failed to branch workflow '{request.workflow_name}': {e!s}"
            import traceback

            traceback.print_exc()
            return BranchWorkflowResultFailure(result_details=details)

    def on_merge_workflow_branch_request(self, request: MergeWorkflowBranchRequest) -> ResultPayload:
        """Merge a branch back into its source workflow, removing the branch when complete."""
        try:
            # Validate branch workflow exists
            branch_workflow = WorkflowRegistry.get_workflow_by_name(request.workflow_name)
        except KeyError as e:
            details = f"Failed to merge workflow branch because it does not exist: {e!s}"
            return MergeWorkflowBranchResultFailure(result_details=details)

        # Get source workflow name from branch metadata
        source_workflow_name = branch_workflow.metadata.branched_from
        if not source_workflow_name:
            details = f"Failed to merge workflow branch '{request.workflow_name}' because it has no source workflow"
            return MergeWorkflowBranchResultFailure(result_details=details)

        # Validate source workflow exists
        try:
            source_workflow = WorkflowRegistry.get_workflow_by_name(source_workflow_name)
        except KeyError:
            details = f"Failed to merge workflow branch '{request.workflow_name}' because source workflow '{source_workflow_name}' does not exist"
            return MergeWorkflowBranchResultFailure(result_details=details)

        try:
            # Create updated metadata for source workflow - update timestamp
            merged_metadata = WorkflowMetadata(
                name=source_workflow_name,
                schema_version=source_workflow.metadata.schema_version,
                engine_version_created_with=source_workflow.metadata.engine_version_created_with,
                node_libraries_referenced=source_workflow.metadata.node_libraries_referenced.copy(),
                node_types_used=source_workflow.metadata.node_types_used.copy(),
                workflows_referenced=source_workflow.metadata.workflows_referenced.copy()
                if source_workflow.metadata.workflows_referenced
                else None,
                description=source_workflow.metadata.description,
                image=source_workflow.metadata.image,
                is_griptape_provided=source_workflow.metadata.is_griptape_provided,
                is_template=source_workflow.metadata.is_template,
                creation_date=source_workflow.metadata.creation_date,
                last_modified_date=datetime.now(tz=UTC),
                branched_from=source_workflow.metadata.branched_from,  # Preserve original source chain
            )

            # Read branch content and replace metadata header with merged metadata
            branch_content_file_path = WorkflowRegistry.get_complete_file_path(branch_workflow.file_path)
            branch_content = Path(branch_content_file_path).read_text(encoding="utf-8")

            # Replace the metadata header with merged metadata
            merged_content = self._replace_workflow_metadata_header(branch_content, merged_metadata)
            if merged_content is None:
                details = f"Failed to replace metadata header for merged workflow '{source_workflow_name}'"
                return MergeWorkflowBranchResultFailure(result_details=details)

            # Write the updated content to the source workflow file
            source_file_path = WorkflowRegistry.get_complete_file_path(source_workflow.file_path)
            Path(source_file_path).write_text(merged_content, encoding="utf-8")

            # Update the registry with new metadata for the source workflow
            source_workflow.metadata = merged_metadata

            # Remove the branch workflow from registry and delete file
            result_messages = []
            try:
                WorkflowRegistry.delete_workflow_by_name(request.workflow_name)
                Path(branch_content_file_path).unlink()
                cleanup_message = f"Deleted branch workflow file and registry entry for '{request.workflow_name}'"
                result_messages.append(ResultDetail(message=cleanup_message, level=logging.INFO))
            except Exception as delete_error:
                warning_message = (
                    f"Failed to fully clean up branch workflow '{request.workflow_name}': {delete_error!s}"
                )
                result_messages.append(ResultDetail(message=warning_message, level=logging.WARNING))
                # Continue anyway - the merge was successful even if cleanup failed

            success_message = f"Successfully merged branch workflow '{request.workflow_name}' into source workflow '{source_workflow_name}'"
            result_messages.append(ResultDetail(message=success_message, level=logging.INFO))

            return MergeWorkflowBranchResultSuccess(
                merged_workflow_name=source_workflow_name, result_details=ResultDetails(*result_messages)
            )

        except Exception as e:
            details = f"Failed to merge branch workflow '{request.workflow_name}' into source workflow '{source_workflow_name}': {e!s}"
            return MergeWorkflowBranchResultFailure(result_details=details)

    def on_reset_workflow_branch_request(self, request: ResetWorkflowBranchRequest) -> ResultPayload:
        """Reset a branch to match its source workflow, discarding branch changes."""
        try:
            # Validate branch workflow exists
            branch_workflow = WorkflowRegistry.get_workflow_by_name(request.workflow_name)
        except KeyError as e:
            details = f"Failed to reset workflow branch because it does not exist: {e!s}"
            return ResetWorkflowBranchResultFailure(result_details=details)

        # Get source workflow name from branch metadata
        source_workflow_name = branch_workflow.metadata.branched_from
        if not source_workflow_name:
            details = f"Failed to reset workflow branch '{request.workflow_name}' because it has no source workflow"
            return ResetWorkflowBranchResultFailure(result_details=details)

        # Validate source workflow exists
        try:
            source_workflow = WorkflowRegistry.get_workflow_by_name(source_workflow_name)
        except KeyError:
            details = f"Failed to reset workflow branch '{request.workflow_name}' because source workflow '{source_workflow_name}' does not exist"
            return ResetWorkflowBranchResultFailure(result_details=details)

        try:
            # Read content from the source workflow (what we're resetting the branch to)
            source_content_file_path = WorkflowRegistry.get_complete_file_path(source_workflow.file_path)
            source_content = Path(source_content_file_path).read_text(encoding="utf-8")

            # Create updated metadata for branch workflow - preserve branch relationship and source timestamp
            reset_metadata = WorkflowMetadata(
                name=request.workflow_name,
                schema_version=source_workflow.metadata.schema_version,
                engine_version_created_with=source_workflow.metadata.engine_version_created_with,
                node_libraries_referenced=source_workflow.metadata.node_libraries_referenced.copy(),
                node_types_used=source_workflow.metadata.node_types_used.copy(),
                workflows_referenced=source_workflow.metadata.workflows_referenced.copy()
                if source_workflow.metadata.workflows_referenced
                else None,
                description=source_workflow.metadata.description,
                image=source_workflow.metadata.image,
                is_griptape_provided=branch_workflow.metadata.is_griptape_provided,
                is_template=branch_workflow.metadata.is_template,
                creation_date=branch_workflow.metadata.creation_date,
                last_modified_date=source_workflow.metadata.last_modified_date,
                branched_from=source_workflow_name,  # Preserve branch relationship
            )

            # Replace the metadata header with reset metadata
            reset_content = self._replace_workflow_metadata_header(source_content, reset_metadata)
            if reset_content is None:
                details = f"Failed to replace metadata header for reset branch workflow '{request.workflow_name}'"
                return ResetWorkflowBranchResultFailure(result_details=details)

            # Write the updated content to the branch workflow file
            branch_content_file_path = WorkflowRegistry.get_complete_file_path(branch_workflow.file_path)
            Path(branch_content_file_path).write_text(reset_content, encoding="utf-8")

            # Update the registry with new metadata for the branch workflow
            branch_workflow.metadata = reset_metadata

        except Exception as e:
            details = f"Failed to reset branch workflow '{request.workflow_name}' to source workflow '{source_workflow_name}': {e!s}"
            return ResetWorkflowBranchResultFailure(result_details=details)
        else:
            details = f"Successfully reset branch workflow '{request.workflow_name}' to match source workflow '{source_workflow_name}'"
            return ResetWorkflowBranchResultSuccess(
                reset_workflow_name=request.workflow_name,
                result_details=ResultDetails(message=details, level=logging.INFO),
            )

    def on_compare_workflows_request(self, request: CompareWorkflowsRequest) -> ResultPayload:
        """Compare two workflows to determine if one is ahead, behind, or up-to-date relative to the other."""
        try:
            # Get the workflow to evaluate
            workflow = WorkflowRegistry.get_workflow_by_name(request.workflow_name)
        except KeyError:
            details = f"Failed to compare workflow '{request.workflow_name}' because it does not exist"
            return CompareWorkflowsResultFailure(result_details=details)

        # Use the provided compare_workflow_name
        compare_workflow_name = request.compare_workflow_name

        # Try to get the source workflow
        try:
            source_workflow = WorkflowRegistry.get_workflow_by_name(compare_workflow_name)
        except KeyError:
            # Source workflow no longer exists
            details = f"Source workflow '{compare_workflow_name}' for '{request.workflow_name}' no longer exists"
            return CompareWorkflowsResultSuccess(
                workflow_name=request.workflow_name,
                compare_workflow_name=compare_workflow_name,
                status="no_source",
                workflow_last_modified=workflow.metadata.last_modified_date.isoformat()
                if workflow.metadata.last_modified_date
                else None,
                source_last_modified=None,
                details=details,
                result_details="Workflow comparison completed successfully.",
            )

        # Compare last modified dates
        workflow_last_modified = workflow.metadata.last_modified_date
        source_last_modified = source_workflow.metadata.last_modified_date

        # Handle missing timestamps
        if workflow_last_modified is None or source_last_modified is None:
            details = f"Cannot compare timestamps - workflow: {workflow_last_modified}, source: {source_last_modified}"
            logger.warning(details)
            return CompareWorkflowsResultSuccess(
                workflow_name=request.workflow_name,
                compare_workflow_name=compare_workflow_name,
                status="diverged",
                workflow_last_modified=workflow_last_modified.isoformat() if workflow_last_modified else None,
                source_last_modified=source_last_modified.isoformat() if source_last_modified else None,
                details=details,
                result_details="Workflow comparison completed successfully.",
            )

        # Compare timestamps to determine status
        if workflow_last_modified == source_last_modified:
            status = "up_to_date"
            details = f"Workflow '{request.workflow_name}' is up-to-date with source '{compare_workflow_name}'"
        elif workflow_last_modified > source_last_modified:
            status = "ahead"
            details = f"Workflow '{request.workflow_name}' is ahead of source '{compare_workflow_name}' (local changes)"
        else:
            status = "behind"
            details = (
                f"Workflow '{request.workflow_name}' is behind source '{compare_workflow_name}' (source has updates)"
            )

        return CompareWorkflowsResultSuccess(
            workflow_name=request.workflow_name,
            compare_workflow_name=compare_workflow_name,
            status=status,
            workflow_last_modified=workflow_last_modified.isoformat(),
            source_last_modified=source_last_modified.isoformat(),
            details=details,
            result_details="Workflow comparison completed successfully.",
        )

    def _walk_object_tree(
        self, obj: Any, process_class_fn: Callable[[type, Any], None], visited: set[int] | None = None
    ) -> None:
        """Recursively walk through object tree, calling process_class_fn for each class found.

        This unified helper handles the common pattern of recursively traversing nested objects
        to find all class instances. Used by both patching and import collection.

        Args:
            obj: Object to traverse (can contain nested lists, dicts, class instances)
            process_class_fn: Function to call for each class found, signature: (class_type, instance)
            visited: Set of object IDs already visited (for circular reference protection)

        Example:
            # Collect all class types in a nested structure
            def collect_type(cls, instance):
                print(f"Found {cls.__name__} instance")

            data = [SomeClass(), {"key": AnotherClass()}]
            self._walk_object_tree(data, collect_type)
        """
        if visited is None:
            visited = set()

        obj_id = id(obj)
        if obj_id in visited:
            return
        visited.add(obj_id)

        # Process the object if it's a class instance
        obj_type = type(obj)
        if isclass(obj_type):
            process_class_fn(obj_type, obj)

        # Recursively traverse containers
        if isinstance(obj, (list, tuple)):
            for item in obj:
                self._walk_object_tree(item, process_class_fn, visited)
        elif isinstance(obj, dict):
            for key, value in obj.items():
                self._walk_object_tree(key, process_class_fn, visited)
                self._walk_object_tree(value, process_class_fn, visited)
        elif hasattr(obj, "__dict__"):
            for attr_value in obj.__dict__.values():
                self._walk_object_tree(attr_value, process_class_fn, visited)

    def _patch_and_pickle_object(self, obj: Any) -> bytes:
        """Patch dynamic module references to stable namespaces, pickle object, then restore.

        This solves the "pickle data was truncated" error that occurs when workflows containing
        objects from dynamically loaded modules (like VideoUrlArtifact, ReferenceImageArtifact)
        are serialized and later reloaded in a fresh Python process.

        The Problem:
            Dynamic modules get names like "gtn_dynamic_module_image_to_video_py_123456789"
            When pickle serializes objects, it embeds these module names in the binary data
            When workflows run later, Python can't import these non-existent module names

        The Solution:
            1. Recursively find all objects from dynamic modules (even nested in containers)
            2. Temporarily patch their __module__ and module_name to stable namespaces
            3. Pickle with stable references like "griptape_nodes.node_libraries.runwayml_library.image_to_video"
            4. Restore original names to avoid side effects

        Args:
            obj: Object to patch and pickle (may contain nested structures)

        Returns:
            Pickled bytes with stable module references

        Example:
            Before: pickle contains "gtn_dynamic_module_image_to_video_py_123456789.VideoUrlArtifact"
            After:  pickle contains "griptape_nodes.node_libraries.runwayml_library.image_to_video.VideoUrlArtifact"
        """
        patched_classes: list[tuple[type, str]] = []
        patched_instances: list[tuple[Any, str]] = []

        def patch_class(class_type: type, instance: Any) -> None:
            """Patch a single class instance to use stable namespace."""
            module = getmodule(class_type)
            if module and GriptapeNodes.LibraryManager().is_dynamic_module(module.__name__):
                stable_namespace = GriptapeNodes.LibraryManager().get_stable_namespace_for_dynamic_module(
                    module.__name__
                )
                if stable_namespace:
                    # Patch class __module__ (affects pickle class reference)
                    if class_type.__module__ != stable_namespace:
                        patched_classes.append((class_type, class_type.__module__))
                        class_type.__module__ = stable_namespace

                    # Patch instance module_name field (affects SerializableMixin serialization)
                    if hasattr(instance, "module_name") and instance.module_name != stable_namespace:
                        patched_instances.append((instance, instance.module_name))
                        instance.module_name = stable_namespace

        try:
            # Apply patches to entire object tree
            self._walk_object_tree(obj, patch_class)
            return pickle.dumps(obj)
        finally:
            # Always restore original names to avoid affecting other code
            for class_obj, original_name in patched_classes:
                class_obj.__module__ = original_name
            for instance_obj, original_name in patched_instances:
                instance_obj.module_name = original_name

    def _collect_object_imports(self, obj: Any, import_recorder: Any, global_modules_set: set[str]) -> None:
        """Recursively collect import statements needed for all classes in object tree.

        This ensures that generated workflows have all necessary import statements,
        including for classes nested deep within containers like ParameterArrays.

        The Process:
            1. Walk through entire object tree (lists, dicts, object attributes)
            2. For each class found, determine the correct import statement
            3. For dynamic modules, use stable namespace imports
            4. For regular modules, use standard imports
            5. Record all imports for workflow generation

        Args:
            obj: Object tree to analyze for required imports
            import_recorder: Collector that will generate the import statements
            global_modules_set: Built-in modules that don't need explicit imports

        Example:
            Input object tree: [ReferenceImageArtifact(), {"data": ImageUrlArtifact()}]
            Generated imports:
                from griptape_nodes.node_libraries.runwayml_library.create_reference_image import ReferenceImageArtifact
                from griptape.artifacts.image_url_artifact import ImageUrlArtifact
        """

        def collect_class_import(class_type: type, _instance: Any) -> None:
            """Collect import statement for a single class."""
            module = getmodule(class_type)
            if module and module.__name__ not in global_modules_set:
                if GriptapeNodes.LibraryManager().is_dynamic_module(module.__name__):
                    # Use stable namespace for dynamic modules
                    stable_namespace = GriptapeNodes.LibraryManager().get_stable_namespace_for_dynamic_module(
                        module.__name__
                    )
                    if stable_namespace:
                        import_recorder.add_from_import(stable_namespace, class_type.__name__)
                    else:
                        msg = f"Missing stable namespace for {module.__name__} type {class_type.__name__}"
                        logger.error(msg)
                        raise RuntimeError(msg)
                else:
                    # Use regular module name for standard modules
                    import_recorder.add_from_import(module.__name__, class_type.__name__)

        self._walk_object_tree(obj, collect_class_import)

    def on_register_workflows_from_config_request(self, request: RegisterWorkflowsFromConfigRequest) -> ResultPayload:
        """Register workflows from a configuration section."""
        try:
            workflows_to_register = GriptapeNodes.ConfigManager().get_config_value(request.config_section)
            if not workflows_to_register:
                details = f"No workflows found in configuration section '{request.config_section}'"
                return RegisterWorkflowsFromConfigResultSuccess(
                    succeeded_workflows=[], failed_workflows=[], result_details=details
                )

            # Process all workflows and track results
            succeeded, failed = self._process_workflows_for_registration(workflows_to_register)

        except Exception as e:
            details = f"Failed to register workflows from configuration section '{request.config_section}': {e!s}"
            return RegisterWorkflowsFromConfigResultFailure(result_details=details)
        else:
            return RegisterWorkflowsFromConfigResultSuccess(
                succeeded_workflows=succeeded,
                failed_workflows=failed,
                result_details=ResultDetails(
                    message=f"Successfully processed workflows: {len(succeeded)} succeeded, {len(failed)} failed.",
                    level=logging.INFO,
                ),
            )

    def _process_workflows_for_registration(self, workflows_to_register: list[str]) -> WorkflowRegistrationResult:  # noqa: C901
        """Process a list of workflow paths for registration.

        Returns:
            WorkflowRegistrationResult with succeeded and failed workflow names
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        succeeded = []
        failed = []

        # First pass: collect all workflow files to determine total count
        all_workflow_files: list[Path] = []

        def collect_workflow_files(path: Path) -> None:
            """Collect workflow files from a path."""
            if not path.exists():
                return
            if path.is_dir():
                for workflow_file in path.rglob("*.py"):
                    if ".venv" in workflow_file.parts:
                        continue
                    # Check if file has workflow metadata
                    try:
                        metadata_blocks = self.get_workflow_metadata(
                            workflow_file, block_name=WorkflowManager.WORKFLOW_METADATA_HEADER
                        )
                        if len(metadata_blocks) == 1:
                            all_workflow_files.append(workflow_file)
                    except Exception as e:
                        # Skip files that can't be read or parsed
                        logger.debug("Skipping workflow file %s due to error: %s", workflow_file, e)
                        continue
            elif path.suffix == ".py":
                try:
                    metadata_blocks = self.get_workflow_metadata(
                        path, block_name=WorkflowManager.WORKFLOW_METADATA_HEADER
                    )
                    if len(metadata_blocks) == 1:
                        all_workflow_files.append(path)
                except Exception as e:
                    logger.debug("Skipping workflow file %s due to error: %s", path, e)

        # Collect all workflow files first
        for workflow_to_register in workflows_to_register:
            collect_workflow_files(Path(workflow_to_register))

        # Track progress
        total_workflows = len(all_workflow_files)

        # Second pass: process each workflow file with progress events
        for current_index, workflow_file in enumerate(all_workflow_files, start=1):
            workflow_name = str(workflow_file.name)

            # Emit loading event
            GriptapeNodes.EventManager().put_event(
                AppEvent(
                    payload=EngineInitializationProgress(
                        phase=InitializationPhase.WORKFLOWS,
                        item_name=workflow_name,
                        status=InitializationStatus.LOADING,
                        current=current_index,
                        total=total_workflows,
                    )
                )
            )

            # Process the workflow
            result_name = self._process_single_workflow_file(workflow_file)
            if result_name:
                succeeded.append(result_name)
                # Emit success event
                GriptapeNodes.EventManager().put_event(
                    AppEvent(
                        payload=EngineInitializationProgress(
                            phase=InitializationPhase.WORKFLOWS,
                            item_name=workflow_name,
                            status=InitializationStatus.COMPLETE,
                            current=current_index,
                            total=total_workflows,
                        )
                    )
                )
            else:
                failed.append(str(workflow_file))
                # Emit failure event
                GriptapeNodes.EventManager().put_event(
                    AppEvent(
                        payload=EngineInitializationProgress(
                            phase=InitializationPhase.WORKFLOWS,
                            item_name=workflow_name,
                            status=InitializationStatus.FAILED,
                            current=current_index,
                            total=total_workflows,
                            error="Failed to process workflow file",
                        )
                    )
                )

        return WorkflowRegistrationResult(succeeded=succeeded, failed=failed)

    def _process_single_workflow_file(self, workflow_file: Path) -> str | None:
        """Process a single workflow file for registration.

        Returns:
            Workflow name if registered successfully, None if failed or skipped
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Parse metadata once and use it for both registration check and actual registration
        load_metadata_request = LoadWorkflowMetadata(file_name=str(workflow_file))
        load_metadata_result = self.on_load_workflow_metadata_request(load_metadata_request)

        if not isinstance(load_metadata_result, LoadWorkflowMetadataResultSuccess):
            logger.debug("Skipping workflow with invalid metadata: %s", workflow_file)
            return None

        workflow_metadata = load_metadata_result.metadata

        # Check if workflow is already registered using the parsed metadata
        if WorkflowRegistry.has_workflow_with_name(workflow_metadata.name):
            logger.debug("Skipping already registered workflow: %s", workflow_file)
            return None

        # Convert to relative path if the workflow is under workspace_path
        config_mgr = GriptapeNodes.ConfigManager()
        workspace_path = config_mgr.workspace_path

        if workflow_file.is_relative_to(workspace_path):
            relative_path = workflow_file.relative_to(workspace_path)
            file_path_to_register = str(relative_path)
        else:
            file_path_to_register = str(workflow_file)

        # Register workflow using existing method with parsed metadata available
        # The _register_workflow method will re-parse metadata, but this is acceptable
        # since we've already validated it's parseable and the duplicate work is minimal
        if self._register_workflow(file_path_to_register):
            return workflow_metadata.name
        return None


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
