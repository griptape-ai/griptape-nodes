from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import platform
import subprocess
import sys
import sysconfig
from collections import defaultdict
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, NamedTuple, TypeVar, cast

from packaging.requirements import InvalidRequirement, Requirement
from pydantic import ValidationError
from rich.align import Align
from rich.box import HEAVY_EDGE
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from semver import Version
from xdg_base_dirs import xdg_data_home

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.node_library.library_registry import (
    CategoryDefinition,
    Library,
    LibraryMetadata,
    LibraryRegistry,
    LibrarySchema,
    NodeDefinition,
    NodeMetadata,
)
from griptape_nodes.retained_mode.events.app_events import (
    AppInitializationComplete,
    EngineInitializationProgress,
    GetEngineVersionRequest,
    GetEngineVersionResultSuccess,
    InitializationPhase,
    InitializationStatus,
)

# Runtime imports for ResultDetails since it's used at runtime
from griptape_nodes.retained_mode.events.base_events import AppEvent, ResultDetails, ResultPayloadFailure
from griptape_nodes.retained_mode.events.config_events import (
    GetConfigCategoryRequest,
    GetConfigCategoryResultSuccess,
    SetConfigCategoryRequest,
    SetConfigCategoryResultSuccess,
)
from griptape_nodes.retained_mode.events.library_events import (
    CheckLibraryUpdateRequest,
    CheckLibraryUpdateResultFailure,
    CheckLibraryUpdateResultSuccess,
    DiscoverLibrariesRequest,
    DiscoverLibrariesResultFailure,
    DiscoverLibrariesResultSuccess,
    DownloadLibraryRequest,
    DownloadLibraryResultFailure,
    DownloadLibraryResultSuccess,
    EvaluateLibraryFitnessRequest,
    EvaluateLibraryFitnessResultFailure,
    EvaluateLibraryFitnessResultSuccess,
    GetAllInfoForAllLibrariesRequest,
    GetAllInfoForAllLibrariesResultFailure,
    GetAllInfoForAllLibrariesResultSuccess,
    GetAllInfoForLibraryRequest,
    GetAllInfoForLibraryResultFailure,
    GetAllInfoForLibraryResultSuccess,
    GetLibraryMetadataRequest,
    GetLibraryMetadataResultFailure,
    GetLibraryMetadataResultSuccess,
    GetNodeMetadataFromLibraryRequest,
    GetNodeMetadataFromLibraryResultFailure,
    GetNodeMetadataFromLibraryResultSuccess,
    InspectLibraryRepoRequest,
    InspectLibraryRepoResultFailure,
    InspectLibraryRepoResultSuccess,
    InstallLibraryDependenciesRequest,
    InstallLibraryDependenciesResultFailure,
    InstallLibraryDependenciesResultSuccess,
    ListCapableLibraryEventHandlersRequest,
    ListCapableLibraryEventHandlersResultFailure,
    ListCapableLibraryEventHandlersResultSuccess,
    ListCategoriesInLibraryRequest,
    ListCategoriesInLibraryResultFailure,
    ListCategoriesInLibraryResultSuccess,
    ListNodeTypesInLibraryRequest,
    ListNodeTypesInLibraryResultFailure,
    ListNodeTypesInLibraryResultSuccess,
    ListRegisteredLibrariesRequest,
    ListRegisteredLibrariesResultSuccess,
    LoadLibrariesRequest,
    LoadLibrariesResultFailure,
    LoadLibrariesResultSuccess,
    LoadLibraryMetadataFromFileRequest,
    LoadLibraryMetadataFromFileResultFailure,
    LoadLibraryMetadataFromFileResultSuccess,
    LoadLibraryRequest,
    LoadLibraryResultFailure,
    LoadLibraryResultSuccess,
    LoadMetadataForAllLibrariesRequest,
    LoadMetadataForAllLibrariesResultSuccess,
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromFileResultFailure,
    RegisterLibraryFromFileResultSuccess,
    RegisterLibraryFromRequirementSpecifierRequest,
    RegisterLibraryFromRequirementSpecifierResultFailure,
    RegisterLibraryFromRequirementSpecifierResultSuccess,
    ReloadAllLibrariesRequest,
    ReloadAllLibrariesResultFailure,
    ReloadAllLibrariesResultSuccess,
    SwitchLibraryRefRequest,
    SwitchLibraryRefResultFailure,
    SwitchLibraryRefResultSuccess,
    SyncLibrariesRequest,
    SyncLibrariesResultFailure,
    SyncLibrariesResultSuccess,
    UnloadLibraryFromRegistryRequest,
    UnloadLibraryFromRegistryResultFailure,
    UnloadLibraryFromRegistryResultSuccess,
    UpdateLibraryRequest,
    UpdateLibraryResultFailure,
    UpdateLibraryResultSuccess,
)
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.events.os_events import (
    DeleteFileRequest,
    DeleteFileResultFailure,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.fitness_problems.libraries import (
    AdvancedLibraryLoadFailureProblem,
    AfterLibraryCallbackProblem,
    BeforeLibraryCallbackProblem,
    CreateConfigCategoryProblem,
    DuplicateLibraryProblem,
    EngineVersionErrorProblem,
    InvalidVersionStringProblem,
    LibraryJsonDecodeProblem,
    LibraryLoadExceptionProblem,
    LibraryNotFoundProblem,
    LibraryProblem,
    LibrarySchemaExceptionProblem,
    LibrarySchemaValidationProblem,
    NodeClassNotBaseNodeProblem,
    NodeClassNotFoundProblem,
    NodeModuleImportProblem,
    OldXdgLocationWarningProblem,
    SandboxDirectoryMissingProblem,
    UpdateConfigCategoryProblem,
)
from griptape_nodes.retained_mode.managers.library_lifecycle.library_directory import LibraryDirectory
from griptape_nodes.retained_mode.managers.library_lifecycle.library_provenance.local_file import (
    LibraryProvenanceLocalFile,
)
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import (
    LibraryFitness,
    LibraryLifecycleState,
)
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.retained_mode.managers.settings import LIBRARIES_TO_DOWNLOAD_KEY, LIBRARIES_TO_REGISTER_KEY
from griptape_nodes.utils.async_utils import subprocess_run
from griptape_nodes.utils.dict_utils import merge_dicts
from griptape_nodes.utils.file_utils import find_file_in_directory
from griptape_nodes.utils.git_utils import (
    GitCloneError,
    GitPullError,
    GitRefError,
    GitRemoteError,
    GitRepositoryError,
    clone_repository,
    extract_repo_name_from_url,
    get_current_ref,
    get_git_remote,
    get_local_commit_sha,
    is_git_url,
    parse_git_url_with_ref,
    switch_branch_or_tag,
    update_library_git,
)
from griptape_nodes.utils.library_utils import (
    LIBRARY_GIT_URLS,
    clone_and_get_library_version,
    filter_old_xdg_library_paths,
    is_monorepo,
)
from griptape_nodes.utils.uv_utils import find_uv_bin
from griptape_nodes.utils.version_utils import get_complete_version_string

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
    from griptape_nodes.retained_mode.events.base_events import Payload, RequestPayload, ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")
console = Console()

# Directories to exclude when scanning for Python source files (in addition to any directory starting with '.')
EXCLUDED_SCAN_DIRECTORIES = frozenset({"venv", "__pycache__"})

TRegisteredEventData = TypeVar("TRegisteredEventData")


class LibraryGitOperationContext(NamedTuple):
    """Context information for git operations on a library."""

    library: Library
    old_version: str
    library_file_path: str
    library_dir: Path


class LibraryUpdateInfo(NamedTuple):
    """Information about a library pending update."""

    library_name: str
    old_version: str
    new_version: str


class LibraryUpdateResult(NamedTuple):
    """Result of updating a single library."""

    library_name: str
    old_version: str
    new_version: str
    result: ResultPayload


class LibraryManager:
    SANDBOX_LIBRARY_NAME = "Sandbox Library"
    LIBRARY_CONFIG_FILENAME = "griptape_nodes_library.json"
    LIBRARY_CONFIG_GLOB_PATTERN = "griptape[_-]nodes[_-]library.json"

    _library_file_path_to_info: dict[str, LibraryInfo]

    @dataclass
    class RegisteredEventHandler(Generic[TRegisteredEventData]):
        """Information regarding an event handler from a registered library.

        The generic type parameter TRegisteredEventData allows each event type
        to specify its own structured additional data.
        """

        handler: Callable[[RequestPayload], ResultPayload]
        library_data: LibrarySchema
        event_data: TRegisteredEventData | None = None

    @dataclass
    class LibraryInfo:
        """Information about a library that was attempted to be loaded.

        Tracks the lifecycle state (where we are in the loading process) and fitness (health/quality).
        Includes the file path and any problems encountered during loading.
        """

        lifecycle_state: LibraryLifecycleState
        fitness: LibraryFitness
        library_path: str
        library_name: str | None = None
        library_version: str | None = None
        problems: list[LibraryProblem] = field(default_factory=list)

    # Stable module namespace mappings for workflow serialization
    # These mappings ensure that dynamically loaded modules can be reliably imported
    # in generated workflow code by providing stable, predictable import paths.
    #
    # Example mappings:
    # dynamic to stable module mapping:
    #     "gtn_dynamic_module_image_to_video_py_123456789": "griptape_nodes.node_libraries.runwayml_library.image_to_video"
    #
    # stable to dynamic module mapping:
    #     "griptape_nodes.node_libraries.runwayml_library.image_to_video": "gtn_dynamic_module_image_to_video_py_123456789"
    #
    # library to stable modules:
    #     "RunwayML Library": {"griptape_nodes.node_libraries.runwayml_library.image_to_video", "griptape_nodes.node_libraries.runwayml_library.text_to_image"},
    #     "Sandbox Library": {"griptape_nodes.node_libraries.sandbox.my_custom_node"}
    #
    _dynamic_to_stable_module_mapping: dict[str, str]  # dynamic_module_name -> stable_namespace
    _stable_to_dynamic_module_mapping: dict[str, str]  # stable_namespace -> dynamic_module_name
    _library_to_stable_modules: dict[str, set[str]]  # library_name -> set of stable_namespaces

    def __init__(self, event_manager: EventManager) -> None:
        self._library_file_path_to_info = {}
        self._dynamic_to_stable_module_mapping = {}
        self._stable_to_dynamic_module_mapping = {}
        self._library_to_stable_modules = {}
        self._library_event_handler_mappings: dict[
            type[Payload], dict[str, LibraryManager.RegisteredEventHandler[Any]]
        ] = {}
        # LibraryDirectory owns the FSMs and manages library lifecycle
        self._library_directory = LibraryDirectory()
        self._libraries_loading_complete = asyncio.Event()

        event_manager.assign_manager_to_request_type(
            ListRegisteredLibrariesRequest, self.on_list_registered_libraries_request
        )
        event_manager.assign_manager_to_request_type(
            ListCapableLibraryEventHandlersRequest, self.on_list_capable_event_handlers
        )
        event_manager.assign_manager_to_request_type(
            ListNodeTypesInLibraryRequest, self.on_list_node_types_in_library_request
        )
        event_manager.assign_manager_to_request_type(
            GetNodeMetadataFromLibraryRequest,
            self.get_node_metadata_from_library_request,
        )
        event_manager.assign_manager_to_request_type(
            LoadLibraryMetadataFromFileRequest,
            self.load_library_metadata_from_file_request,
        )
        event_manager.assign_manager_to_request_type(
            RegisterLibraryFromFileRequest,
            self.register_library_from_file_request,
        )
        event_manager.assign_manager_to_request_type(
            RegisterLibraryFromRequirementSpecifierRequest, self.register_library_from_requirement_specifier_request
        )
        event_manager.assign_manager_to_request_type(
            ListCategoriesInLibraryRequest,
            self.list_categories_in_library_request,
        )
        event_manager.assign_manager_to_request_type(
            GetLibraryMetadataRequest,
            self.get_library_metadata_request,
        )
        event_manager.assign_manager_to_request_type(GetAllInfoForLibraryRequest, self.get_all_info_for_library_request)
        event_manager.assign_manager_to_request_type(
            GetAllInfoForAllLibrariesRequest, self.on_get_all_info_for_all_libraries_request
        )
        event_manager.assign_manager_to_request_type(
            LoadMetadataForAllLibrariesRequest, self.load_metadata_for_all_libraries_request
        )
        event_manager.assign_manager_to_request_type(
            UnloadLibraryFromRegistryRequest, self.unload_library_from_registry_request
        )
        event_manager.assign_manager_to_request_type(ReloadAllLibrariesRequest, self.reload_libraries_request)
        event_manager.assign_manager_to_request_type(LoadLibrariesRequest, self.load_libraries_request)
        event_manager.assign_manager_to_request_type(CheckLibraryUpdateRequest, self.check_library_update_request)
        event_manager.assign_manager_to_request_type(UpdateLibraryRequest, self.update_library_request)
        event_manager.assign_manager_to_request_type(SwitchLibraryRefRequest, self.switch_library_ref_request)
        event_manager.assign_manager_to_request_type(DownloadLibraryRequest, self.download_library_request)
        event_manager.assign_manager_to_request_type(
            InstallLibraryDependenciesRequest, self.install_library_dependencies_request
        )
        event_manager.assign_manager_to_request_type(SyncLibrariesRequest, self.sync_libraries_request)
        event_manager.assign_manager_to_request_type(InspectLibraryRepoRequest, self.inspect_library_repo_request)

        event_manager.add_listener_to_app_event(
            AppInitializationComplete,
            self.on_app_initialization_complete,
        )

    def print_library_load_status(self) -> None:
        library_file_paths = self.get_libraries_attempted_to_load()
        library_infos = []
        for library_file_path in library_file_paths:
            library_info = self.get_library_info_for_attempted_load(library_file_path)
            library_infos.append(library_info)

        console = Console()

        # Check if the list is empty
        if not library_infos:
            # Display a message indicating no libraries are available
            empty_message = Text("No library information available", style="italic")
            panel = Panel(empty_message, title="Library Information", border_style="blue")
            console.print(panel)
            return

        # Create a table with two columns and row dividers
        table = Table(show_header=True, box=HEAVY_EDGE, show_lines=True, expand=True)
        table.add_column("Library", style="green", ratio=1)
        table.add_column("Problems", style="yellow", ratio=1)

        # Status emojis mapping
        status_emoji = {
            LibraryFitness.GOOD: "[green]OK[/green]",
            LibraryFitness.FLAWED: "[yellow]![/yellow]",
            LibraryFitness.UNUSABLE: "[red]X[/red]",
            LibraryFitness.MISSING: "[red]?[/red]",
        }

        # Status text mapping (colored)
        status_text = {
            LibraryFitness.GOOD: "[green](GOOD)[/green]",
            LibraryFitness.FLAWED: "[yellow](FLAWED)[/yellow]",
            LibraryFitness.UNUSABLE: "[red](UNUSABLE)[/red]",
            LibraryFitness.MISSING: "[red](MISSING)[/red]",
        }

        # Add rows for each library info
        for lib_info in library_infos:
            # Library column with emoji, name, version, colored status, and file path underneath
            emoji = status_emoji.get(lib_info.fitness, "ERROR: Unknown/Unexpected Library Status")
            colored_status = status_text.get(lib_info.fitness, "(UNKNOWN)")
            name = lib_info.library_name if lib_info.library_name else "*UNKNOWN*"

            library_version = lib_info.library_version
            if library_version:
                version_str = str(library_version)
            else:
                version_str = "*UNKNOWN*"

            file_path = lib_info.library_path
            library_name_with_details = Text.from_markup(
                f"{emoji} - {name} v{version_str} {colored_status}\n[cyan dim]{file_path}[/cyan dim]"
            )
            library_name_with_details.overflow = "fold"

            # Problems column - collate by type then format
            if not lib_info.problems:
                problems = "No problems detected."
            else:
                # Group problems by type
                problems_by_type = defaultdict(list)
                for problem in lib_info.problems:
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
                    # Number the problems when there's more than one
                    problems = "\n".join([f"{j + 1}. {problem}" for j, problem in enumerate(collated_strings)])

            # Add the row to the table
            table.add_row(library_name_with_details, problems)

        # Create a panel containing the table
        panel = Panel(table, title="Library Information", border_style="blue")

        # Display the panel
        console.print(panel)

    def get_libraries_attempted_to_load(self) -> list[str]:
        return list(self._library_file_path_to_info.keys())

    def get_library_info_for_attempted_load(self, library_file_path: str) -> LibraryInfo:
        return self._library_file_path_to_info[library_file_path]

    def get_library_info_by_library_name(self, library_name: str) -> LibraryInfo | None:
        for library_info in self._library_file_path_to_info.values():
            if library_info.library_name == library_name:
                return library_info
        return None

    def on_register_event_handler(
        self,
        request_type: type[RequestPayload],
        handler: Callable[[RequestPayload], ResultPayload],
        library_data: LibrarySchema,
        event_data: object | None = None,
    ) -> None:
        """Register an event handler for a specific request type from a library.

        Args:
            request_type: The type of request payload this handler processes
            handler: The callable handler function
            library_data: Schema data for the library registering this handler
            event_data: Optional structured data specific to this event type
        """
        if self._library_event_handler_mappings.get(request_type) is None:
            self._library_event_handler_mappings[request_type] = {}
        self._library_event_handler_mappings[request_type][library_data.name] = LibraryManager.RegisteredEventHandler(
            handler=handler, library_data=library_data, event_data=event_data
        )

    def get_registered_event_handlers(self, request_type: type[Payload]) -> dict[str, RegisteredEventHandler[Any]]:
        """Get all registered event handlers for a specific request type."""
        return self._library_event_handler_mappings.get(request_type, {})

    def on_list_capable_event_handlers(self, request: ListCapableLibraryEventHandlersRequest) -> ResultPayload:
        """Get all registered event handlers for a specific request type."""
        request_type = PayloadRegistry.get_type(request.request_type)
        if request_type is None:
            details = f"Request type '{request.request_type}' is not registered in the PayloadRegistry."
            return ListCapableLibraryEventHandlersResultFailure(exception=KeyError(details), result_details=details)
        handler_mappings = self.get_registered_event_handlers(request_type)
        return ListCapableLibraryEventHandlersResultSuccess(
            handlers=list(handler_mappings.keys()),
            result_details=f"Successfully listed {len(handler_mappings)} capable library event handlers",
        )

    def on_list_registered_libraries_request(self, _request: ListRegisteredLibrariesRequest) -> ResultPayload:
        # Make a COPY of the list
        snapshot_list = LibraryRegistry.list_libraries()
        event_copy = snapshot_list.copy()

        details = "Successfully retrieved the list of registered libraries."

        result = ListRegisteredLibrariesResultSuccess(
            libraries=event_copy,
            result_details=details,
        )
        return result

    def on_list_node_types_in_library_request(self, request: ListNodeTypesInLibraryRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to list node types in a Library named '{request.library}'. Failed because no Library with that name was registered."

            result = ListNodeTypesInLibraryResultFailure(result_details=details)
            return result

        # Cool, get a copy of the list.
        snapshot_list = library.get_registered_nodes()
        event_copy = snapshot_list.copy()

        details = f"Successfully retrieved the list of node types in the Library named '{request.library}'."

        result = ListNodeTypesInLibraryResultSuccess(
            node_types=event_copy,
            result_details=details,
        )
        return result

    def get_library_metadata_request(self, request: GetLibraryMetadataRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get metadata for Library '{request.library}'. Failed because no Library with that name was registered."

            result = GetLibraryMetadataResultFailure(result_details=details)
            return result

        # Get the metadata off of it.
        metadata = library.get_metadata()
        details = f"Successfully retrieved metadata for Library '{request.library}'."

        result = GetLibraryMetadataResultSuccess(metadata=metadata, result_details=details)
        return result

    def load_library_metadata_from_file_request(  # noqa: PLR0911
        self, request: LoadLibraryMetadataFromFileRequest
    ) -> LoadLibraryMetadataFromFileResultSuccess | LoadLibraryMetadataFromFileResultFailure:
        """Load library metadata from a JSON file without loading the actual node modules.

        This method provides a lightweight way to get library schema information
        without the overhead of dynamically importing Python modules.
        """
        file_path = request.file_path

        # Convert to Path object if it's a string
        json_path = Path(file_path)

        # Check if the file exists
        if not json_path.exists():
            details = f"Attempted to load Library JSON file. Failed because no file could be found at the specified path: {json_path}"
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=None,
                status=LibraryFitness.MISSING,
                problems=[LibraryNotFoundProblem(library_path=str(json_path))],
                result_details=details,
            )

        # Load the JSON
        try:
            with json_path.open("r", encoding="utf-8") as f:
                library_json = json.load(f)
        except json.JSONDecodeError:
            details = f"Attempted to load Library JSON file. Failed because the file at path '{json_path}' was improperly formatted."
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=None,
                status=LibraryFitness.UNUSABLE,
                problems=[LibraryJsonDecodeProblem()],
                result_details=details,
            )
        except Exception as err:
            details = f"Attempted to load Library JSON file from location '{json_path}'. Failed because an exception occurred: {err}"
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=None,
                status=LibraryFitness.UNUSABLE,
                problems=[LibraryLoadExceptionProblem(error_message=str(err))],
                result_details=details,
            )

        # Try to extract library name from JSON for better error reporting
        library_name = library_json.get("name") if isinstance(library_json, dict) else None

        # Do you comport, my dude
        try:
            library_data = LibrarySchema.model_validate(library_json)
        except ValidationError as err:
            # Do some more hardcore error handling.
            problems = []
            for error in err.errors():
                loc = " -> ".join(map(str, error["loc"]))
                msg = error["msg"]
                error_type = error["type"]
                problem = LibrarySchemaValidationProblem(location=loc, error_type=error_type, message=msg)
                problems.append(problem)
            details = f"Attempted to load Library JSON file. Failed because the file at path '{json_path}' failed to match the library schema due to: {err}"
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=library_name,
                status=LibraryFitness.UNUSABLE,
                problems=problems,
                result_details=details,
            )
        except Exception as err:
            details = f"Attempted to load Library JSON file. Failed because the file at path '{json_path}' failed to match the library schema due to: {err}"
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=library_name,
                status=LibraryFitness.UNUSABLE,
                problems=[LibrarySchemaExceptionProblem(error_message=str(err))],
                result_details=details,
            )

        # Make sure the version string is copacetic.
        library_version = library_data.metadata.library_version
        if library_version is None:
            details = f"Attempted to load Library '{library_data.name}' JSON file from '{json_path}'. Failed because version string '{library_data.metadata.library_version}' wasn't valid. Must be in major.minor.patch format."
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=library_data.name,
                status=LibraryFitness.UNUSABLE,
                problems=[InvalidVersionStringProblem(version_string=str(library_data.metadata.library_version))],
                result_details=details,
            )

        # Get git remote and ref if this library is in a git repository
        library_dir = json_path.parent.absolute()
        git_remote = get_git_remote(library_dir)
        try:
            git_ref = get_current_ref(library_dir)
        except GitRefError as e:
            logger.debug("Failed to get git ref for %s: %s", library_dir, e)
            git_ref = None

        details = f"Successfully loaded library metadata from JSON file at {json_path}"
        return LoadLibraryMetadataFromFileResultSuccess(
            library_schema=library_data,
            file_path=file_path,
            git_remote=git_remote,
            git_ref=git_ref,
            result_details=details,
        )

    def load_metadata_for_all_libraries_request(self, request: LoadMetadataForAllLibrariesRequest) -> ResultPayload:  # noqa: ARG002
        """Load metadata for all libraries from configuration without loading node modules.

        This loads metadata from both library JSON files specified in configuration
        and generates sandbox library metadata by scanning Python files without importing them.
        """
        successful_libraries = []
        failed_libraries = []

        # Discover library files for metadata loading
        library_files = self._discover_library_files()

        # Load metadata for all discovered library files
        for library_file in library_files:
            metadata_request = LoadLibraryMetadataFromFileRequest(file_path=str(library_file))
            metadata_result = self.load_library_metadata_from_file_request(metadata_request)

            if isinstance(metadata_result, LoadLibraryMetadataFromFileResultSuccess):
                successful_libraries.append(metadata_result)
            else:
                failed_libraries.append(cast("LoadLibraryMetadataFromFileResultFailure", metadata_result))

        # Generate sandbox library metadata
        sandbox_result = self._generate_sandbox_library_metadata()
        if isinstance(sandbox_result, LoadLibraryMetadataFromFileResultSuccess):
            successful_libraries.append(sandbox_result)
        elif isinstance(sandbox_result, LoadLibraryMetadataFromFileResultFailure):
            failed_libraries.append(sandbox_result)
        # If sandbox_result is None, sandbox was not configured or no files found - skip it

        details = (
            f"Successfully loaded metadata for {len(successful_libraries)} libraries, {len(failed_libraries)} failed"
        )
        return LoadMetadataForAllLibrariesResultSuccess(
            successful_libraries=successful_libraries,
            failed_libraries=failed_libraries,
            result_details=details,
        )

    def _generate_sandbox_library_metadata(
        self,
    ) -> LoadLibraryMetadataFromFileResultSuccess | LoadLibraryMetadataFromFileResultFailure | None:
        """Generate sandbox library metadata by scanning Python files without importing them.

        Returns None if no sandbox directory is configured or no files are found.
        """
        config_mgr = GriptapeNodes.ConfigManager()
        sandbox_library_subdir = config_mgr.get_config_value("sandbox_library_directory")
        if not sandbox_library_subdir:
            logger.debug("No sandbox directory specified in config. Skipping sandbox library metadata generation.")
            return None

        # Prepend the workflow directory; if the sandbox dir starts with a slash, the workflow dir will be ignored.
        sandbox_library_dir = config_mgr.workspace_path / sandbox_library_subdir
        sandbox_library_dir_as_posix = sandbox_library_dir.as_posix()

        if not sandbox_library_dir.exists():
            details = "Sandbox directory does not exist. If you wish to create a Sandbox directory to develop custom nodes: in the Griptape Nodes editor, go to Settings -> Libraries and navigate to the Sandbox Settings."
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=sandbox_library_dir_as_posix,
                library_name=LibraryManager.SANDBOX_LIBRARY_NAME,
                status=LibraryFitness.MISSING,
                problems=[SandboxDirectoryMissingProblem()],
                result_details=ResultDetails(message=details, level=logging.INFO),
            )

        sandbox_node_candidates = self._find_files_in_dir(directory=sandbox_library_dir, extension=".py")
        if not sandbox_node_candidates:
            logger.debug(
                "No candidate files found in sandbox directory '%s'. Skipping sandbox library metadata generation.",
                sandbox_library_dir,
            )
            return None

        # For metadata-only generation, we create placeholder node definitions
        # based on file names since we can't inspect the classes without importing
        node_definitions = []
        for candidate in sandbox_node_candidates:
            # Use the full file name (with extension) as a placeholder to make it clear this is a file candidate
            file_name = candidate.name

            # Create a placeholder node definition - we can't get the actual class metadata
            # without importing, so we use defaults
            node_metadata = NodeMetadata(
                category="Griptape Nodes Sandbox",
                description=f"'{file_name}' may contain one or more nodes defined in this candidate file.",
                display_name=file_name,
                icon="square-dashed",
                color=None,
            )
            node_definition = NodeDefinition(
                class_name=file_name,
                file_path=str(candidate),
                metadata=node_metadata,
            )
            node_definitions.append(node_definition)

        if not node_definitions:
            logger.debug(
                "No valid node files found in sandbox directory '%s'. Skipping sandbox library metadata generation.",
                sandbox_library_dir,
            )
            return None

        # Create the library schema
        sandbox_category = CategoryDefinition(
            title="Sandbox",
            description=f"Nodes loaded from the {LibraryManager.SANDBOX_LIBRARY_NAME}.",
            color="#c7621a",
            icon="Folder",
        )

        engine_version = GriptapeNodes().handle_engine_version_request(request=GetEngineVersionRequest())
        if not isinstance(engine_version, GetEngineVersionResultSuccess):
            details = "Could not get engine version for sandbox library generation."
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=sandbox_library_dir_as_posix,
                library_name=LibraryManager.SANDBOX_LIBRARY_NAME,
                status=LibraryFitness.UNUSABLE,
                problems=[EngineVersionErrorProblem()],
                result_details=details,
            )

        engine_version_str = f"{engine_version.major}.{engine_version.minor}.{engine_version.patch}"
        library_metadata = LibraryMetadata(
            author="Author needs to be specified when library is published.",
            description="Nodes loaded from the sandbox library.",
            library_version=engine_version_str,
            engine_version=engine_version_str,
            tags=["sandbox"],
            is_griptape_nodes_searchable=False,
        )
        categories = [
            {"Griptape Nodes Sandbox": sandbox_category},
        ]
        library_schema = LibrarySchema(
            name=LibraryManager.SANDBOX_LIBRARY_NAME,
            library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
            metadata=library_metadata,
            categories=categories,
            nodes=node_definitions,
        )

        # Get git remote and ref if the sandbox directory is in a git repository
        git_remote = get_git_remote(sandbox_library_dir)
        try:
            git_ref = get_current_ref(sandbox_library_dir)
        except GitRefError as e:
            logger.debug("Failed to get git ref for sandbox library %s: %s", sandbox_library_dir, e)
            git_ref = None

        details = f"Successfully generated sandbox library metadata with {len(node_definitions)} nodes from {sandbox_library_dir}"
        return LoadLibraryMetadataFromFileResultSuccess(
            library_schema=library_schema,
            file_path=str(sandbox_library_dir),
            git_remote=git_remote,
            git_ref=git_ref,
            result_details=details,
        )

    def get_node_metadata_from_library_request(self, request: GetNodeMetadataFromLibraryRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get node metadata for a node type '{request.node_type}' in a Library named '{request.library}'. Failed because no Library with that name was registered."
            result = GetNodeMetadataFromLibraryResultFailure(result_details=details)
            return result

        # Does the node type exist within the library?
        try:
            metadata = library.get_node_metadata(node_type=request.node_type)
        except KeyError:
            details = f"Attempted to get node metadata for a node type '{request.node_type}' in a Library named '{request.library}'. Failed because no node type of that name could be found in the Library."
            result = GetNodeMetadataFromLibraryResultFailure(result_details=details)
            return result

        details = f"Successfully retrieved node metadata for a node type '{request.node_type}' in a Library named '{request.library}'."

        result = GetNodeMetadataFromLibraryResultSuccess(
            metadata=metadata,
            result_details=details,
        )
        return result

    def list_categories_in_library_request(self, request: ListCategoriesInLibraryRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get categories in a Library named '{request.library}'. Failed because no Library with that name was registered."
            result = ListCategoriesInLibraryResultFailure(result_details=details)
            return result

        categories = library.get_categories()
        result = ListCategoriesInLibraryResultSuccess(
            categories=categories, result_details=f"Successfully retrieved categories for library '{request.library}'."
        )
        return result

    async def register_library_from_file_request(self, request: RegisterLibraryFromFileRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915 (complex logic needs branches)
        file_path = request.file_path

        # Convert to Path object if it's a string
        json_path = Path(file_path)

        # Check if the file exists
        if not json_path.exists():
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                lifecycle_state=LibraryLifecycleState.FAILURE,
                library_path=file_path,
                library_name=None,
                fitness=LibraryFitness.MISSING,
                problems=[LibraryNotFoundProblem(library_path=file_path)],
            )
            details = f"Attempted to load Library JSON file. Failed because no file could be found at the specified path: {json_path}"
            return RegisterLibraryFromFileResultFailure(result_details=details)

        # Use the new metadata loading functionality
        metadata_request = LoadLibraryMetadataFromFileRequest(file_path=file_path)
        metadata_result = self.load_library_metadata_from_file_request(metadata_request)

        if not isinstance(metadata_result, LoadLibraryMetadataFromFileResultSuccess):
            # Metadata loading failed, use the detailed error information from the failure result
            failure_result = cast("LoadLibraryMetadataFromFileResultFailure", metadata_result)

            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                lifecycle_state=LibraryLifecycleState.FAILURE,
                library_path=file_path,
                library_name=failure_result.library_name,
                fitness=failure_result.status,
                problems=failure_result.problems,
            )
            return RegisterLibraryFromFileResultFailure(result_details=str(failure_result.result_details))

        # Get the validated library data
        library_data = metadata_result.library_schema
        library_version = library_data.metadata.library_version

        # Get the directory containing the JSON file to resolve relative paths
        base_dir = json_path.parent.absolute()
        # Add the directory to the Python path to allow for relative imports
        sys.path.insert(0, str(base_dir))

        # Install dependencies and add library venv to sys.path if library has dependencies
        if library_data.metadata.dependencies and library_data.metadata.dependencies.pip_dependencies:
            venv_path = self._get_library_venv_path(library_data.name, file_path)

            install_request = InstallLibraryDependenciesRequest(library_file_path=file_path)
            install_result = await self.install_library_dependencies_request(install_request)

            if isinstance(install_result, InstallLibraryDependenciesResultFailure):
                details = (
                    f"Failed to install dependencies for library '{library_data.name}': {install_result.result_details}"
                )
                return RegisterLibraryFromFileResultFailure(result_details=details)

            if isinstance(install_result, InstallLibraryDependenciesResultSuccess):
                logger.info(
                    "Installed %d dependencies for library '%s'",
                    install_result.dependencies_installed,
                    library_data.name,
                )

            # Add venv site-packages to sys.path so node imports can find dependencies
            if venv_path.exists():
                site_packages = str(
                    Path(
                        sysconfig.get_path(
                            "purelib",
                            vars={"base": str(venv_path), "platbase": str(venv_path)},
                        )
                    )
                )
                sys.path.insert(0, site_packages)
                logger.debug("Added library '%s' venv to sys.path: %s", library_data.name, site_packages)

        # Load the advanced library module if specified
        advanced_library_instance = None
        if library_data.advanced_library_path:
            try:
                advanced_library_instance = self._load_advanced_library_module(
                    library_data=library_data,
                    base_dir=base_dir,
                )
            except Exception as err:
                self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                    lifecycle_state=LibraryLifecycleState.FAILURE,
                    library_path=file_path,
                    library_name=library_data.name,
                    library_version=library_version,
                    fitness=LibraryFitness.UNUSABLE,
                    problems=[
                        AdvancedLibraryLoadFailureProblem(
                            advanced_library_path=library_data.advanced_library_path, error_message=str(err)
                        )
                    ],
                )
                details = f"Attempted to load Library '{library_data.name}' from '{json_path}'. Failed to load Advanced Library module: {err}"
                return RegisterLibraryFromFileResultFailure(result_details=details)

        # Create or get the library
        try:
            # Try to create a new library
            library = LibraryRegistry.generate_new_library(
                library_data=library_data,
                mark_as_default_library=request.load_as_default_library,
                advanced_library=advanced_library_instance,
            )

        except KeyError as err:
            # Library already exists
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                lifecycle_state=LibraryLifecycleState.FAILURE,
                library_path=file_path,
                library_name=library_data.name,
                library_version=library_version,
                fitness=LibraryFitness.UNUSABLE,
                problems=[DuplicateLibraryProblem()],
            )

            details = f"Attempted to load Library JSON file from '{json_path}'. Failed because a Library '{library_data.name}' already exists. Error: {err}."
            return RegisterLibraryFromFileResultFailure(result_details=details)

        # We are at least potentially viable.
        # Record all problems that occurred
        problems = []

        # Check the library's custom config settings.
        if library_data.settings is not None:
            # Assign them into the config space.
            for library_data_setting in library_data.settings:
                # Does the category exist?
                get_category_request = GetConfigCategoryRequest(
                    category=library_data_setting.category,
                    failure_log_level=logging.DEBUG,  # Missing category is expected, suppress error toast
                )
                get_category_result = GriptapeNodes.handle_request(get_category_request)
                if not isinstance(get_category_result, GetConfigCategoryResultSuccess):
                    # That's OK, we'll invent it. Or at least we'll try.
                    create_new_category_request = SetConfigCategoryRequest(
                        category=library_data_setting.category, contents=library_data_setting.contents
                    )
                    create_new_category_result = GriptapeNodes.handle_request(create_new_category_request)
                    if not isinstance(create_new_category_result, SetConfigCategoryResultSuccess):
                        problems.append(CreateConfigCategoryProblem(category_name=library_data_setting.category))
                        details = f"Failed attempting to create new config category '{library_data_setting.category}' for library '{library_data.name}'."
                        logger.error(details)
                        continue  # SKIP IT
                else:
                    # We had an existing category. Union our changes into it (not replacing anything that matched).
                    existing_category_contents = merge_dicts(
                        library_data_setting.contents, get_category_result.contents, add_keys=True, merge_lists=True
                    )
                    set_category_request = SetConfigCategoryRequest(
                        category=library_data_setting.category, contents=existing_category_contents
                    )
                    set_category_result = GriptapeNodes.handle_request(set_category_request)
                    if not isinstance(set_category_result, SetConfigCategoryResultSuccess):
                        problems.append(UpdateConfigCategoryProblem(category_name=library_data_setting.category))
                        details = f"Failed attempting to update config category '{library_data_setting.category}' for library '{library_data.name}'."
                        logger.error(details)
                        continue  # SKIP IT

        # Attempt to load nodes from the library.
        library_load_results = await asyncio.to_thread(
            self._attempt_load_nodes_from_library,
            library_data=library_data,
            library=library,
            base_dir=base_dir,
            library_file_path=file_path,
            library_version=library_version,
            problems=problems,
        )
        self._library_file_path_to_info[file_path] = library_load_results

        match library_load_results.fitness:
            case LibraryFitness.GOOD:
                details = f"Successfully loaded Library '{library_data.name}' from JSON file at {json_path}"
                return RegisterLibraryFromFileResultSuccess(
                    library_name=library_data.name, result_details=ResultDetails(message=details, level=logging.INFO)
                )
            case LibraryFitness.FLAWED:
                details = f"Successfully loaded Library JSON file from '{json_path}', but one or more nodes failed to load. Check the log for more details."
                return RegisterLibraryFromFileResultSuccess(
                    library_name=library_data.name, result_details=ResultDetails(message=details, level=logging.WARNING)
                )
            case LibraryFitness.UNUSABLE:
                details = f"Attempted to load Library JSON file from '{json_path}'. Failed because no nodes were loaded. Check the log for more details."
                return RegisterLibraryFromFileResultFailure(result_details=details)
            case _:
                details = f"Attempted to load Library JSON file from '{json_path}'. Failed because an unknown/unexpected fitness '{library_load_results.fitness}' was returned."
                return RegisterLibraryFromFileResultFailure(result_details=details)

    async def register_library_from_requirement_specifier_request(
        self, request: RegisterLibraryFromRequirementSpecifierRequest
    ) -> ResultPayload:
        try:
            package_name = Requirement(request.requirement_specifier).name
            # Determine venv path for dependency installation
            venv_path = self._get_library_venv_path(package_name, None)

            # Check if venv already exists before initialization
            venv_already_exists = venv_path.exists()

            # Only install dependencies if conditions are met
            try:
                library_python_venv_path = await self._init_library_venv(venv_path)
            except RuntimeError as e:
                details = f"Attempted to install library '{request.requirement_specifier}'. Failed when creating the virtual environment: {e}"
                return RegisterLibraryFromRequirementSpecifierResultFailure(result_details=details)

            if venv_already_exists:
                logger.debug(
                    "Skipping dependency installation for package '%s' - venv already exists at %s",
                    package_name,
                    venv_path,
                )
            elif self._can_write_to_venv_location(library_python_venv_path):
                # Check disk space before installing dependencies
                config_manager = GriptapeNodes.ConfigManager()
                min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_libraries")
                if not OSManager.check_available_disk_space(Path(venv_path), min_space_gb):
                    error_msg = OSManager.format_disk_space_error(Path(venv_path))
                    details = f"Attempted to install library '{request.requirement_specifier}'. Failed when installing dependencies due to insufficient disk space (requires {min_space_gb} GB): {error_msg}"
                    return RegisterLibraryFromRequirementSpecifierResultFailure(result_details=details)

                uv_path = find_uv_bin()

                logger.info("Installing dependency '%s' with pip in venv at %s", package_name, venv_path)
                is_debug = config_manager.get_config_value("log_level").upper() == "DEBUG"
                await subprocess_run(
                    [
                        uv_path,
                        "pip",
                        "install",
                        request.requirement_specifier,
                        "--python",
                        str(library_python_venv_path),
                    ],
                    check=True,
                    capture_output=not is_debug,
                    text=True,
                )
            else:
                logger.debug(
                    "Skipping dependency installation for package '%s' - venv location at %s is not writable",
                    package_name,
                    venv_path,
                )
        except subprocess.CalledProcessError as e:
            details = f"Attempted to install library '{request.requirement_specifier}'. Failed: return code={e.returncode}, stdout={e.stdout}, stderr={e.stderr}"
            return RegisterLibraryFromRequirementSpecifierResultFailure(result_details=details)
        except InvalidRequirement as e:
            details = f"Attempted to install library '{request.requirement_specifier}'. Failed due to invalid requirement specifier: {e}"
            return RegisterLibraryFromRequirementSpecifierResultFailure(result_details=details)

        library_path = str(files(package_name).joinpath(request.library_config_name))

        register_result = GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path=library_path))
        if isinstance(register_result, RegisterLibraryFromFileResultFailure):
            details = f"Attempted to install library '{request.requirement_specifier}'. Failed due to {register_result}"
            return RegisterLibraryFromRequirementSpecifierResultFailure(result_details=details)

        return RegisterLibraryFromRequirementSpecifierResultSuccess(
            library_name=request.requirement_specifier,
            result_details=f"Successfully registered library from requirement specifier: {request.requirement_specifier}",
        )

    async def _init_library_venv(self, library_venv_path: Path) -> Path:
        """Initialize a virtual environment for the library.

        If the virtual environment already exists, it will not be recreated.

        Args:
            library_venv_path: Path to the virtual environment directory

        Returns:
            Path to the Python executable in the virtual environment

        Raises:
            RuntimeError: If the virtual environment cannot be created.
        """
        # Create a virtual environment for the library
        python_version = platform.python_version()

        if library_venv_path.exists():
            logger.debug("Virtual environment already exists at %s", library_venv_path)
        else:
            # Check disk space before creating virtual environment
            config_manager = GriptapeNodes.ConfigManager()
            min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_libraries")
            if not OSManager.check_available_disk_space(library_venv_path.parent, min_space_gb):
                error_msg = OSManager.format_disk_space_error(library_venv_path.parent)
                logger.error(
                    "Attempted to create virtual environment (requires %.1f GB). Failed: %s", min_space_gb, error_msg
                )
                error_message = (
                    f"Disk space error creating virtual environment (requires {min_space_gb} GB): {error_msg}"
                )
                raise RuntimeError(error_message)

            try:
                uv_path = find_uv_bin()
                logger.info("Creating virtual environment at %s with Python %s", library_venv_path, python_version)
                is_debug = config_manager.get_config_value("log_level").upper() == "DEBUG"
                await subprocess_run(
                    [uv_path, "venv", str(library_venv_path), "--python", python_version],
                    check=True,
                    capture_output=not is_debug,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                msg = f"Failed to create virtual environment at {library_venv_path} with Python {python_version}: return code={e.returncode}, stdout={e.stdout}, stderr={e.stderr}"
                raise RuntimeError(msg) from e
            logger.debug("Created virtual environment at %s", library_venv_path)

        # Grab the python executable from the virtual environment so that we can pip install there
        if OSManager.is_windows():
            library_venv_python_path = library_venv_path / "Scripts" / "python.exe"
        else:
            library_venv_python_path = library_venv_path / "bin" / "python"

        return library_venv_python_path

    def _get_library_venv_path(self, library_name: str, library_file_path: str | None = None) -> Path:
        """Get the path to the virtual environment directory for a library.

        Args:
            library_name: Name of the library
            library_file_path: Optional path to the library JSON file

        Returns:
            Path to the virtual environment directory
        """
        clean_library_name = library_name.replace(" ", "_").strip()

        if library_file_path is not None:
            # Create venv relative to the library.json file
            library_dir = Path(library_file_path).parent.absolute()
            return library_dir / ".venv"

        # Create venv relative to the xdg data home
        return xdg_data_home() / "griptape_nodes" / "libraries" / clean_library_name / ".venv"

    def _can_write_to_venv_location(self, venv_python_path: Path) -> bool:
        """Check if we can write to the venv location (either create it or modify existing).

        Args:
            venv_python_path: Path to the python executable in the virtual environment

        Returns:
            True if we can write to the location, False otherwise
        """
        # On Windows, permission checks are hard. Assume we can write
        if OSManager.is_windows():
            return True

        venv_path = venv_python_path.parent.parent

        # If venv doesn't exist, check if parent directory is writable
        if not venv_path.exists():
            parent_dir = venv_path.parent
            try:
                return parent_dir.exists() and os.access(parent_dir, os.W_OK)
            except (OSError, AttributeError) as e:
                logger.debug("Could not check parent directory permissions for %s: %s", parent_dir, e)
                return False

        # If venv exists, check if we can write to it
        try:
            return os.access(venv_path, os.W_OK)
        except (OSError, AttributeError) as e:
            logger.debug("Could not check venv write permissions for %s: %s", venv_path, e)
            return False

    def unload_library_from_registry_request(self, request: UnloadLibraryFromRegistryRequest) -> ResultPayload:
        try:
            LibraryRegistry.unregister_library(library_name=request.library_name)
        except Exception as e:
            details = f"Attempted to unload library '{request.library_name}'. Failed due to {e}"
            return UnloadLibraryFromRegistryResultFailure(result_details=details)

        # Clean up all stable module aliases for this library
        self._unregister_all_stable_module_aliases_for_library(request.library_name)

        # Remove the library from our library info list. This prevents it from still showing
        # up in the table of attempted library loads.
        lib_info = self.get_library_info_by_library_name(request.library_name)
        if lib_info:
            del self._library_file_path_to_info[lib_info.library_path]
        details = f"Successfully unloaded (and unregistered) library '{request.library_name}'."
        return UnloadLibraryFromRegistryResultSuccess(result_details=details)

    def get_all_info_for_all_libraries_request(self, request: GetAllInfoForAllLibrariesRequest) -> ResultPayload:  # noqa: ARG002
        list_libraries_request = ListRegisteredLibrariesRequest()
        list_libraries_result = self.on_list_registered_libraries_request(list_libraries_request)

        if not list_libraries_result.succeeded():
            details = "Attempted to get all info for all libraries, but listing the registered libraries failed."
            return GetAllInfoForAllLibrariesResultFailure(result_details=details)

        try:
            list_libraries_success = cast("ListRegisteredLibrariesResultSuccess", list_libraries_result)

            # Create a mapping of library name to all its info.
            library_name_to_all_info = {}

            for library_name in list_libraries_success.libraries:
                library_all_info_request = GetAllInfoForLibraryRequest(library=library_name)
                library_all_info_result = self.get_all_info_for_library_request(library_all_info_request)

                if not library_all_info_result.succeeded():
                    details = f"Attempted to get all info for all libraries, but failed when getting all info for library named '{library_name}'."
                    return GetAllInfoForAllLibrariesResultFailure(result_details=details)

                library_all_info_success = cast("GetAllInfoForLibraryResultSuccess", library_all_info_result)

                library_name_to_all_info[library_name] = library_all_info_success
        except Exception as err:
            details = f"Attempted to get all info for all libraries. Encountered error {err}."
            return GetAllInfoForAllLibrariesResultFailure(result_details=details)

        # We're home free now
        details = "Successfully retrieved all info for all libraries."
        result = GetAllInfoForAllLibrariesResultSuccess(
            library_name_to_library_info=library_name_to_all_info, result_details=details
        )
        return result

    async def on_get_all_info_for_all_libraries_request(
        self, request: GetAllInfoForAllLibrariesRequest
    ) -> ResultPayload:
        """Async handler for GetAllInfoForAllLibrariesRequest that waits for library loading to complete."""
        await self._libraries_loading_complete.wait()
        return await asyncio.to_thread(self.get_all_info_for_all_libraries_request, request)

    def get_all_info_for_library_request(self, request: GetAllInfoForLibraryRequest) -> ResultPayload:  # noqa: PLR0911
        # Does this library exist?
        try:
            LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed because no Library with that name was registered."
            result = GetAllInfoForLibraryResultFailure(result_details=details)
            return result

        library_metadata_request = GetLibraryMetadataRequest(library=request.library)
        library_metadata_result = self.get_library_metadata_request(library_metadata_request)

        if not library_metadata_result.succeeded():
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the library's metadata."
            return GetAllInfoForLibraryResultFailure(result_details=details)

        list_categories_request = ListCategoriesInLibraryRequest(library=request.library)
        list_categories_result = self.list_categories_in_library_request(list_categories_request)

        if not list_categories_result.succeeded():
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the list of categories in the library."
            return GetAllInfoForLibraryResultFailure(result_details=details)

        node_type_list_request = ListNodeTypesInLibraryRequest(library=request.library)
        node_type_list_result = self.on_list_node_types_in_library_request(node_type_list_request)

        if not node_type_list_result.succeeded():
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the list of node types in the library."
            return GetAllInfoForLibraryResultFailure(result_details=details)

        # Cast everyone to their success counterparts.
        try:
            library_metadata_result_success = cast("GetLibraryMetadataResultSuccess", library_metadata_result)
            list_categories_result_success = cast("ListCategoriesInLibraryResultSuccess", list_categories_result)
            node_type_list_result_success = cast("ListNodeTypesInLibraryResultSuccess", node_type_list_result)
        except Exception as err:
            details = (
                f"Attempted to get all library info for a Library named '{request.library}'. Encountered error: {err}."
            )
            return GetAllInfoForLibraryResultFailure(result_details=details)

        # Now build the map of node types to metadata.
        node_type_name_to_node_metadata_details = {}
        for node_type_name in node_type_list_result_success.node_types:
            node_metadata_request = GetNodeMetadataFromLibraryRequest(library=request.library, node_type=node_type_name)
            node_metadata_result = self.get_node_metadata_from_library_request(node_metadata_request)

            if not node_metadata_result.succeeded():
                details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the metadata for a node type called '{node_type_name}'."
                return GetAllInfoForLibraryResultFailure(result_details=details)

            try:
                node_metadata_result_success = cast("GetNodeMetadataFromLibraryResultSuccess", node_metadata_result)
            except Exception as err:
                details = f"Attempted to get all library info for a Library named '{request.library}'. Encountered error: {err}."
                return GetAllInfoForLibraryResultFailure(result_details=details)

            # Put it into the map.
            node_type_name_to_node_metadata_details[node_type_name] = node_metadata_result_success

        details = f"Successfully got all library info for a Library named '{request.library}'."
        result = GetAllInfoForLibraryResultSuccess(
            library_metadata_details=library_metadata_result_success,
            category_details=list_categories_result_success,
            node_type_name_to_node_metadata_details=node_type_name_to_node_metadata_details,
            result_details=details,
        )
        return result

    def _create_stable_namespace(self, library_name: str, file_path: Path) -> str:
        """Create a stable namespace for a dynamic module.

        Args:
            library_name: Name of the library
            file_path: Path to the Python file

        Returns:
            Stable namespace string like 'griptape_nodes.node_libraries.runwayml_library.image_to_video'
        """
        # Convert library name to safe module name
        safe_library_name = library_name.lower().replace(" ", "_").replace("-", "_")
        # Remove invalid characters
        safe_library_name = "".join(c for c in safe_library_name if c.isalnum() or c == "_")

        # Convert file path to safe module name
        safe_file_name = file_path.stem.replace("-", "_")

        return f"griptape_nodes.node_libraries.{safe_library_name}.{safe_file_name}"

    def _register_stable_module_alias(
        self, dynamic_module_name: str, stable_namespace: str, module: ModuleType, library_name: str
    ) -> None:
        """Register a stable alias for a dynamic module in sys.modules.

        Args:
            dynamic_module_name: Original dynamic module name
            stable_namespace: Stable namespace to alias to
            module: The loaded module
            library_name: Name of the library
        """
        # Update our mapping
        self._dynamic_to_stable_module_mapping[dynamic_module_name] = stable_namespace
        self._stable_to_dynamic_module_mapping[stable_namespace] = dynamic_module_name

        # Track library-to-modules mapping for bulk cleanup
        library_key = library_name
        if library_key not in self._library_to_stable_modules:
            self._library_to_stable_modules[library_key] = set()
        self._library_to_stable_modules[library_key].add(stable_namespace)

        # Register the stable alias in sys.modules
        sys.modules[stable_namespace] = module

        details = f"Registered stable alias: {stable_namespace} -> {dynamic_module_name} (library: {library_key})"
        logger.debug(details)

    def _unregister_stable_module_alias(self, dynamic_module_name: str) -> None:
        """Unregister a stable alias for a dynamic module during hot reload.

        Args:
            dynamic_module_name: Original dynamic module name
        """
        if dynamic_module_name in self._dynamic_to_stable_module_mapping:
            stable_namespace = self._dynamic_to_stable_module_mapping[dynamic_module_name]

            # Remove from sys.modules if it exists
            if stable_namespace in sys.modules:
                del sys.modules[stable_namespace]

            # Remove from library tracking
            for library_modules in self._library_to_stable_modules.values():
                library_modules.discard(stable_namespace)

            # Remove from our mappings
            del self._dynamic_to_stable_module_mapping[dynamic_module_name]
            del self._stable_to_dynamic_module_mapping[stable_namespace]

            details = f"Unregistered stable alias: {stable_namespace}"
            logger.debug(details)

    def _unregister_all_stable_module_aliases_for_library(self, library_name: str) -> None:
        """Unregister all stable module aliases for a library during library unload/reload.

        Args:
            library_name: Name of the library to clean up
        """
        library_key = library_name
        if library_key not in self._library_to_stable_modules:
            return

        stable_namespaces = self._library_to_stable_modules[library_key].copy()
        details = f"Unregistering {len(stable_namespaces)} stable aliases for library: {library_name}"
        logger.debug(details)

        for stable_namespace in stable_namespaces:
            # Remove from sys.modules if it exists
            if stable_namespace in sys.modules:
                del sys.modules[stable_namespace]

            # Find and remove from dynamic mapping
            dynamic_module_name = self._stable_to_dynamic_module_mapping.get(stable_namespace)
            if dynamic_module_name:
                self._dynamic_to_stable_module_mapping.pop(dynamic_module_name, None)
            self._stable_to_dynamic_module_mapping.pop(stable_namespace, None)

        # Clear the library's module set
        del self._library_to_stable_modules[library_key]
        details = f"Completed cleanup of stable aliases for library: '{library_name}'."
        logger.debug(details)

    def get_stable_namespace_for_dynamic_module(self, dynamic_module_name: str) -> str | None:
        """Get the stable namespace for a dynamic module name.

        This method is used during workflow serialization to convert dynamic module names
        (like "gtn_dynamic_module_image_to_video_py_123456789") to stable namespace imports
        (like "griptape_nodes.node_libraries.runwayml_library.image_to_video").

        Args:
            dynamic_module_name: The dynamic module name to look up

        Returns:
            The stable namespace string, or None if not found

        Example:
            >>> manager.get_stable_namespace_for_dynamic_module("gtn_dynamic_module_image_to_video_py_123456789")
            "griptape_nodes.node_libraries.runwayml_library.image_to_video"
        """
        return self._dynamic_to_stable_module_mapping.get(dynamic_module_name)

    def is_dynamic_module(self, module_name: str) -> bool:
        """Check if a module name represents a dynamically loaded module.

        Args:
            module_name: The module name to check

        Returns:
            True if this is a dynamic module name, False otherwise

        Example:
            >>> manager.is_dynamic_module("gtn_dynamic_module_image_to_video_py_123456789")
            True
            >>> manager.is_dynamic_module("griptape.artifacts")
            False
        """
        return module_name.startswith("gtn_dynamic_module_")

    @staticmethod
    def _get_root_cause_from_exception(exception: BaseException) -> BaseException:
        """Walk the exception chain to find the root cause.

        Args:
            exception: The exception to walk

        Returns:
            The root cause exception (the innermost exception in the chain)
        """
        current = exception
        while current.__cause__ is not None:
            current = current.__cause__
        return current

    def _load_module_from_file(self, file_path: Path | str, library_name: str) -> ModuleType:
        """Dynamically load a module from a Python file with support for hot reloading.

        Args:
            file_path: Path to the Python file
            library_name: Name of the library

        Returns:
            The loaded module

        Raises:
            ImportError: If the module cannot be imported
        """
        # Ensure file_path is a Path object
        file_path = Path(file_path)

        # Generate a unique module name
        module_name = f"gtn_dynamic_module_{file_path.name.replace('.', '_')}_{hash(str(file_path))}"

        # Create stable namespace
        stable_namespace = self._create_stable_namespace(library_name, file_path)

        # Check if this module is already loaded
        if module_name in sys.modules:
            # For dynamically loaded modules, we need to re-create the module
            # with a fresh spec rather than using importlib.reload

            # Unregister old stable alias
            self._unregister_stable_module_alias(module_name)

            # Remove the old module from sys.modules
            old_module = sys.modules.pop(module_name)

            # Create a fresh spec and module
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                msg = f"Could not load module specification from {file_path}"
                raise ImportError(msg)

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            try:
                # Execute the module with the new code
                spec.loader.exec_module(module)
                # Register new stable alias
                self._register_stable_module_alias(module_name, stable_namespace, module, library_name)
                details = f"Hot reloaded module: {module_name} from {file_path}"
                logger.debug(details)
            except Exception as e:
                # Restore the old module in case of failure
                sys.modules[module_name] = old_module
                msg = f"Error reloading module {module_name} from {file_path}: {e}"
                raise ImportError(msg) from e

        # Load it for the first time
        else:
            # Load the module specification
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                msg = f"Could not load module specification from {file_path}"
                raise ImportError(msg)

            # Create the module
            module = importlib.util.module_from_spec(spec)

            # Add to sys.modules to handle recursive imports
            sys.modules[module_name] = module

            # Execute the module
            try:
                spec.loader.exec_module(module)
                # Register stable alias
                self._register_stable_module_alias(module_name, stable_namespace, module, library_name)
            except Exception as err:
                msg = f"Module at '{file_path}' failed to load with error: {err}"
                raise ImportError(msg) from err

        return module

    def _load_class_from_file(self, file_path: Path | str, class_name: str, library_name: str) -> type[BaseNode]:
        """Dynamically load a class from a Python file with support for hot reloading.

        Args:
            file_path: Path to the Python file
            class_name: Name of the class to load
            library_name: Name of the library

        Returns:
            The loaded class

        Raises:
            ImportError: If the module cannot be imported
            AttributeError: If the class doesn't exist in the module
            TypeError: If the loaded class isn't a BaseNode-derived class
        """
        try:
            module = self._load_module_from_file(file_path, library_name)
        except ImportError as err:
            msg = f"Attempted to load class '{class_name}'. Error: {err}"
            raise ImportError(msg) from err

        # Get the class
        try:
            node_class = getattr(module, class_name)
        except AttributeError as err:
            msg = f"Class '{class_name}' not found in module '{file_path}'"
            raise AttributeError(msg) from err

        # Verify it's a BaseNode subclass
        if not issubclass(node_class, BaseNode):
            msg = f"'{class_name}' must inherit from BaseNode"
            raise TypeError(msg)

        return node_class

    async def load_all_libraries_from_config(self) -> None:
        self._libraries_loading_complete.clear()

        try:
            # Load metadata for all libraries to determine which ones can be safely loaded
            metadata_request = LoadMetadataForAllLibrariesRequest()
            metadata_result = self.load_metadata_for_all_libraries_request(metadata_request)

            # Check if metadata loading succeeded
            if not isinstance(metadata_result, LoadMetadataForAllLibrariesResultSuccess):
                logger.error("Failed to load metadata for all libraries, skipping library registration")
                return

            # Record all failed libraries in our tracking immediately
            for failed_library in metadata_result.failed_libraries:
                self._library_file_path_to_info[failed_library.library_path] = LibraryManager.LibraryInfo(
                    lifecycle_state=LibraryLifecycleState.FAILURE,
                    library_path=failed_library.library_path,
                    library_name=failed_library.library_name,
                    fitness=failed_library.status,
                    problems=failed_library.problems,
                )

            # Calculate total libraries for progress tracking
            total_libraries = len(metadata_result.successful_libraries)

            # Use metadata results to selectively load libraries
            for current_library_index, library_result in enumerate(metadata_result.successful_libraries, start=1):
                library_name = library_result.library_schema.name

                # Emit loading event
                GriptapeNodes.EventManager().put_event(
                    AppEvent(
                        payload=EngineInitializationProgress(
                            phase=InitializationPhase.LIBRARIES,
                            item_name=library_name,
                            status=InitializationStatus.LOADING,
                            current=current_library_index,
                            total=total_libraries,
                        )
                    )
                )

                # Register the library
                if library_result.library_schema.name == LibraryManager.SANDBOX_LIBRARY_NAME:
                    # Handle sandbox library - use the schema we already have
                    await self._attempt_generate_sandbox_library_from_schema(
                        library_schema=library_result.library_schema, sandbox_directory=library_result.file_path
                    )
                    # Emit success event for sandbox library
                    GriptapeNodes.EventManager().put_event(
                        AppEvent(
                            payload=EngineInitializationProgress(
                                phase=InitializationPhase.LIBRARIES,
                                item_name=library_name,
                                status=InitializationStatus.COMPLETE,
                                current=current_library_index,
                                total=total_libraries,
                            )
                        )
                    )
                else:
                    # Handle config-based library - register it directly using the file path
                    register_request = RegisterLibraryFromFileRequest(
                        file_path=library_result.file_path, load_as_default_library=False
                    )
                    register_result = await self.register_library_from_file_request(register_request)
                    if isinstance(register_result, RegisterLibraryFromFileResultFailure):
                        # Registration failed - the failure info is already recorded in _library_file_path_to_info
                        # by register_library_from_file_request, so we just log it here for visibility
                        logger.warning("Failed to register library from %s", library_result.file_path)
                        # Emit failure event
                        error_message = (
                            register_result.result_details.result_details[0].message
                            if isinstance(register_result.result_details, ResultDetails)
                            else register_result.result_details
                        )
                        GriptapeNodes.EventManager().put_event(
                            AppEvent(
                                payload=EngineInitializationProgress(
                                    phase=InitializationPhase.LIBRARIES,
                                    item_name=library_name,
                                    status=InitializationStatus.FAILED,
                                    current=current_library_index,
                                    total=total_libraries,
                                    error=error_message,
                                )
                            )
                        )
                    else:
                        # Emit success event
                        GriptapeNodes.EventManager().put_event(
                            AppEvent(
                                payload=EngineInitializationProgress(
                                    phase=InitializationPhase.LIBRARIES,
                                    item_name=library_name,
                                    status=InitializationStatus.COMPLETE,
                                    current=current_library_index,
                                    total=total_libraries,
                                )
                            )
                        )

            # Print 'em all pretty
            self.print_library_load_status()

            # Remove any missing libraries AFTER we've printed them for the user.
            user_libraries_section = LIBRARIES_TO_REGISTER_KEY
            self._remove_missing_libraries_from_config(config_category=user_libraries_section)
        finally:
            self._libraries_loading_complete.set()

    async def _ensure_libraries_from_config(self) -> None:
        """Ensure libraries from git URLs specified in config are downloaded.

        This method:
        1. Reads libraries_to_download from config
        2. Downloads any missing libraries concurrently
        3. Logs summary of successful/failed operations

        Supports URL format with @ref suffix (e.g., "https://github.com/user/repo@stable").
        Libraries are registered later by load_all_libraries_from_config().
        """
        config_mgr = GriptapeNodes.ConfigManager()
        git_urls = config_mgr.get_config_value(LIBRARIES_TO_DOWNLOAD_KEY, default=[])

        if not git_urls:
            logger.debug("No libraries to download from config")
            return

        logger.info("Starting download of %d libraries from config", len(git_urls))

        # Use shared download method
        results = await self._download_libraries_from_git_urls(git_urls)

        # Count successes and failures
        successful = sum(1 for r in results.values() if r["success"])
        failed = len(results) - successful

        logger.info(
            "Completed automatic library downloads: %d successful, %d failed",
            successful,
            failed,
        )

    async def _download_libraries_from_git_urls(
        self,
        git_urls_with_refs: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Download multiple libraries from git URLs concurrently.

        Args:
            git_urls_with_refs: List of git URLs with optional @ref suffix (e.g., "url@v1.0")

        Returns:
            Dictionary mapping git_url_with_ref to result info:
            {
                "url@ref": {
                    "success": bool,
                    "library_name": str | None,
                    "error": str | None,
                    "skipped": bool (optional, True if already exists),
                }
            }
        """
        config_mgr = GriptapeNodes.ConfigManager()
        libraries_dir_setting = config_mgr.get_config_value("libraries_directory")

        if not libraries_dir_setting:
            logger.warning("Cannot download libraries: libraries_directory not configured")
            return {}

        libraries_path = config_mgr.workspace_path / libraries_dir_setting

        async def download_one(git_url_with_ref: str) -> tuple[str, dict[str, Any]]:
            """Download a single library if not already present."""
            # Parse URL to extract git URL and optional ref
            git_url, ref = parse_git_url_with_ref(git_url_with_ref)
            target_directory_name = extract_repo_name_from_url(git_url)
            target_path = libraries_path / target_directory_name

            # Skip if already exists
            if target_path.exists():
                logger.info("Library at '%s' already exists, skipping", target_path)
                return git_url_with_ref, {
                    "success": False,
                    "library_name": None,
                    "error": None,
                    "skipped": True,
                }

            logger.info("Downloading library from '%s'", git_url_with_ref)
            download_result = await GriptapeNodes.ahandle_request(
                DownloadLibraryRequest(
                    git_url=git_url,
                    branch_tag_commit=ref,
                    fail_on_exists=False,
                    auto_register=False,
                )
            )

            if isinstance(download_result, DownloadLibraryResultSuccess):
                logger.info("Downloaded library '%s'", download_result.library_name)
                return git_url_with_ref, {
                    "success": True,
                    "library_name": download_result.library_name,
                    "error": None,
                }

            error = str(download_result.result_details)
            logger.warning("Failed to download '%s': %s", git_url_with_ref, error)
            return git_url_with_ref, {
                "success": False,
                "library_name": None,
                "error": error,
            }

        # Download all concurrently
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(download_one(url)) for url in git_urls_with_refs]

        # Collect results
        return dict(task.result() for task in tasks)

    async def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        # Automatically migrate old XDG library paths from config
        # TODO: Remove https://github.com/griptape-ai/griptape-nodes/issues/3348
        self._migrate_old_xdg_library_paths()

        # App just got init'd. First download any missing libraries from git URLs.
        await self._ensure_libraries_from_config()

        # Now load all libraries from config (including newly downloaded ones)
        await self.load_all_libraries_from_config()

        # Register all secrets now that libraries are loaded and settings are merged
        GriptapeNodes.SecretsManager().register_all_secrets()

        # We have to load all libraries before we attempt to load workflows.

        # Load workflows specified by libraries.
        library_workflow_files_to_register = []
        library_result = self.on_list_registered_libraries_request(ListRegisteredLibrariesRequest())
        if isinstance(library_result, ListRegisteredLibrariesResultSuccess):
            for library_name in library_result.libraries:
                try:
                    library = LibraryRegistry.get_library(name=library_name)
                except KeyError:
                    # Skip it.
                    logger.error("Could not find library '%s'", library_name)
                    continue
                library_data = library.get_library_data()
                if library_data.workflows:
                    # Prepend the library's JSON path to the list, as the workflows are stored
                    # relative to it.
                    # Find the library info with that name.
                    for library_info in self._library_file_path_to_info.values():
                        if library_info.library_name == library_name:
                            library_path = Path(library_info.library_path)
                            base_dir = library_path.parent.absolute()
                            # Add the directory to the Python path to allow for relative imports.
                            sys.path.insert(0, str(base_dir))
                            for workflow in library_data.workflows:
                                final_workflow_path = base_dir / workflow
                                library_workflow_files_to_register.append(str(final_workflow_path))
                            # WE DONE HERE (at least, for this library).
                            break
        # This will (attempts to) load all workflows specified by LIBRARIES. User workflows are loaded later.
        GriptapeNodes.WorkflowManager().register_list_of_workflows(library_workflow_files_to_register)

        # Go tell the Workflow Manager that it's turn is now.
        GriptapeNodes.WorkflowManager().on_libraries_initialization_complete()

        # Print the engine ready message
        engine_version = get_complete_version_string()

        # Get current session ID
        session_id = GriptapeNodes.get_session_id()
        session_info = f" | Session: {session_id[:8]}..." if session_id else " | No Session"

        # Get user and organization
        user = GriptapeNodes.UserManager().user
        user_info = f" | User: {user.email if user else 'Not available'}"

        user_organization = GriptapeNodes.UserManager().user_organization
        org_info = f" | Org: {user_organization.name if user_organization else 'Not available'}"

        nodes_app_url = os.getenv("GRIPTAPE_NODES_UI_BASE_URL", "https://nodes.griptape.ai")
        message = Panel(
            Align.center(
                f"[bold green]Engine is ready to receive events[/bold green]\n"
                f"[bold blue]Return to: [link={nodes_app_url}]{nodes_app_url}[/link] to access the Workflow Editor[/bold blue]",
                vertical="middle",
            ),
            title="Griptape Nodes Engine Started",
            subtitle=f"[green]Version: {engine_version}{session_info}{user_info}{org_info}[/green]",
            border_style="green",
            padding=(1, 4),
        )
        console.print(message)

    async def _load_libraries_from_provenance_system(self) -> None:
        """Load libraries using the new provenance-based system with FSM.

        This method converts libraries_to_register entries into LibraryProvenanceLocalFile
        objects and processes them through the LibraryDirectory and LibraryLifecycleFSM systems.
        """
        # Get config manager
        config_mgr = GriptapeNodes.ConfigManager()

        # Get the current libraries_to_register list
        user_libraries_section = LIBRARIES_TO_REGISTER_KEY
        libraries_to_register: list[str] = config_mgr.get_config_value(user_libraries_section)

        # Filter out empty or whitespace-only entries
        original_count = len(libraries_to_register) if libraries_to_register else 0
        libraries_to_register = [path for path in (libraries_to_register or []) if path and path.strip()]
        filtered_count = original_count - len(libraries_to_register)
        if filtered_count > 0:
            logger.warning("Filtered out %d empty library path entries from configuration", filtered_count)

        if not libraries_to_register:
            logger.info("No libraries to register from config")
            return

        # Convert string paths to LibraryProvenanceLocalFile objects
        for library_path in libraries_to_register:
            # Skip non-JSON files for now (requirement specifiers will need different handling)
            if not library_path.endswith(".json"):
                logger.debug("Skipping non-JSON library path: %s", library_path)
                continue

            # Create provenance object
            provenance = LibraryProvenanceLocalFile(file_path=library_path)

            # Add to directory as user candidate (defaults to active=True)
            # This automatically creates FSM and runs evaluation
            await self._library_directory.add_user_candidate(provenance)

            logger.debug("Added library provenance: %s", provenance.get_display_name())

        # Get all candidates for evaluation
        all_candidates = self._library_directory.get_all_candidates()

        logger.info("Evaluated %d library candidates through FSM lifecycle", len(all_candidates))

        # Report on conflicts found
        self._report_library_name_conflicts()

        # Get candidates that are ready for installation
        installable_candidates = self._library_directory.get_installable_candidates()

        # Log any skipped libraries
        active_candidates = self._library_directory.get_active_candidates()
        for candidate in active_candidates:
            if candidate not in installable_candidates:
                blockers = self._library_directory.get_installation_blockers(candidate.provenance)
                if blockers:
                    blocker_messages = [blocker.message for blocker in blockers]
                    combined_message = "; ".join(blocker_messages)
                    logger.info("Skipping library '%s' - %s", candidate.provenance.get_display_name(), combined_message)

        logger.info("Installing and loading %d installable library candidates", len(installable_candidates))

        # Process installable candidates through installation and loading
        for candidate in installable_candidates:
            if await self._library_directory.install_library(candidate.provenance):
                await self._library_directory.load_library(candidate.provenance)

    def _report_library_name_conflicts(self) -> None:
        """Report on library name conflicts found during evaluation."""
        conflicting_names = self._library_directory.get_all_conflicting_library_names()
        for library_name in conflicting_names:
            conflicting_provenances = self._library_directory.get_conflicting_provenances(library_name)
            logger.warning(
                "Library name conflict detected for '%s' across %d libraries: %s",
                library_name,
                len(conflicting_provenances),
                [p.get_display_name() for p in conflicting_provenances],
            )

    def _load_advanced_library_module(
        self,
        library_data: LibrarySchema,
        base_dir: Path,
    ) -> AdvancedNodeLibrary | None:
        """Load the advanced library module and return an instance.

        Args:
            library_data: The library schema data
            base_dir: Base directory containing the library files

        Returns:
            An instance of the AdvancedNodeLibrary class from the module, or None if not specified

        Raises:
            ImportError: If the module cannot be loaded
            AttributeError: If no AdvancedNodeLibrary subclass is found
            TypeError: If the found class cannot be instantiated
        """
        from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary

        if not library_data.advanced_library_path:
            return None

        # Resolve relative path to absolute path
        advanced_library_module_path = Path(library_data.advanced_library_path)
        if not advanced_library_module_path.is_absolute():
            advanced_library_module_path = base_dir / advanced_library_module_path

        # Load the module (supports hot reloading)
        try:
            module = self._load_module_from_file(advanced_library_module_path, library_data.name)
        except Exception as err:
            msg = f"Failed to load Advanced Library module from '{advanced_library_module_path}': {err}"
            raise ImportError(msg) from err

        # Find an AdvancedNodeLibrary subclass in the module
        advanced_library_class = None
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, AdvancedNodeLibrary)
                and obj is not AdvancedNodeLibrary
                and obj.__module__ == module.__name__
            ):
                advanced_library_class = obj
                break

        if not advanced_library_class:
            msg = f"No AdvancedNodeLibrary subclass found in Advanced Library module '{advanced_library_module_path}'"
            raise AttributeError(msg)

        # Create an instance
        try:
            advanced_library_instance = advanced_library_class()
        except Exception as err:
            msg = f"Failed to instantiate AdvancedNodeLibrary class '{advanced_library_class.__name__}': {err}"
            raise TypeError(msg) from err

        # Validate the instance
        if not isinstance(advanced_library_instance, AdvancedNodeLibrary):
            msg = f"Created instance is not an AdvancedNodeLibrary subclass: {type(advanced_library_instance)}"
            raise TypeError(msg)

        return advanced_library_instance

    def _attempt_load_nodes_from_library(  # noqa: PLR0913, PLR0912, PLR0915, C901
        self,
        library_data: LibrarySchema,
        library: Library,
        base_dir: Path,
        library_file_path: str,
        library_version: str | None,
        problems: list[LibraryProblem],
    ) -> LibraryInfo:
        any_nodes_loaded_successfully = False

        # Check if library is in old XDG location
        old_xdg_libraries_path = xdg_data_home() / "griptape_nodes" / "libraries"
        library_path_obj = Path(library_file_path)
        try:
            # Check if the library path is relative to the old XDG location
            if library_path_obj.is_relative_to(old_xdg_libraries_path):
                problems.append(OldXdgLocationWarningProblem(old_path=str(library_path_obj)))
                logger.warning(
                    "Library '%s' is located in old XDG data directory: %s. "
                    "Starting with version 0.65.0, libraries are managed in your workspace directory. "
                    "To migrate: run 'gtn init' (CLI) or go to App Settings and click 'Re-run Setup Wizard' (desktop app).",
                    library_data.name,
                    library_file_path,
                )
        except ValueError:
            # is_relative_to() raises ValueError if paths are on different drives
            # In this case, library is definitely not in the old XDG location
            pass

        # Call the before_library_nodes_loaded callback if available
        advanced_library = library.get_advanced_library()
        if advanced_library:
            try:
                advanced_library.before_library_nodes_loaded(library_data, library)
                details = f"Successfully called before_library_nodes_loaded callback for library '{library_data.name}'"
                logger.debug(details)
            except Exception as err:
                problems.append(BeforeLibraryCallbackProblem(error_message=str(err)))
                details = (
                    f"Failed to call before_library_nodes_loaded callback for library '{library_data.name}': {err}"
                )
                logger.error(details)

        # Process each node in the metadata
        for node_definition in library_data.nodes:
            # Resolve relative path to absolute path
            node_file_path = Path(node_definition.file_path)
            if not node_file_path.is_absolute():
                node_file_path = base_dir / node_file_path

            try:
                # Dynamically load the module containing the node class
                node_class = self._load_class_from_file(node_file_path, node_definition.class_name, library_data.name)
            except ImportError as err:
                root_cause = self._get_root_cause_from_exception(err)
                problems.append(
                    NodeModuleImportProblem(
                        class_name=node_definition.class_name,
                        file_path=str(node_file_path),
                        error_message=str(err),
                        root_cause=str(root_cause),
                    )
                )
                details = f"Attempted to load node '{node_definition.class_name}' from '{node_file_path}'. Failed because module could not be imported: {err}"
                logger.error(details)
                continue  # SKIP IT
            except AttributeError:
                problems.append(
                    NodeClassNotFoundProblem(class_name=node_definition.class_name, file_path=str(node_file_path))
                )
                details = f"Attempted to load node '{node_definition.class_name}' from '{node_file_path}'. Failed because class not found in module"
                logger.error(details)
                continue  # SKIP IT
            except TypeError:
                problems.append(
                    NodeClassNotBaseNodeProblem(class_name=node_definition.class_name, file_path=str(node_file_path))
                )
                details = f"Attempted to load node '{node_definition.class_name}' from '{node_file_path}'. Failed because class doesn't inherit from BaseNode"
                logger.error(details)
                continue  # SKIP IT

            # Register the node type with the library
            library_problem = library.register_new_node_type(node_class, metadata=node_definition.metadata)
            if library_problem is not None:
                problems.append(library_problem)

            # If we got here, at least one node came in.
            any_nodes_loaded_successfully = True

        # Call the after_library_nodes_loaded callback if available
        if advanced_library:
            try:
                advanced_library.after_library_nodes_loaded(library_data, library)
                details = f"Successfully called after_library_nodes_loaded callback for library '{library_data.name}'"
                logger.debug(details)
            except Exception as err:
                problems.append(AfterLibraryCallbackProblem(error_message=str(err)))
                details = f"Failed to call after_library_nodes_loaded callback for library '{library_data.name}': {err}"
                logger.error(details)

        # Create a LibraryInfo object based on load successes and problem count.
        if not any_nodes_loaded_successfully:
            status = LibraryFitness.UNUSABLE
        elif problems:
            # Success, but errors.
            status = LibraryFitness.FLAWED
        else:
            # Flawless victory.
            status = LibraryFitness.GOOD

        # Create a LibraryInfo object based on load successes and problem count.
        return LibraryManager.LibraryInfo(
            lifecycle_state=LibraryLifecycleState.LOADED,
            library_path=library_file_path,
            library_name=library_data.name,
            library_version=library_version,
            fitness=status,
            problems=problems,
        )

    async def _attempt_generate_sandbox_library_from_schema(
        self, library_schema: LibrarySchema, sandbox_directory: str
    ) -> None:
        """Generate sandbox library using an existing schema, loading actual node classes."""
        sandbox_library_dir = Path(sandbox_directory)
        sandbox_library_dir_as_posix = sandbox_library_dir.as_posix()

        problems = []

        # Get the file paths from the schema's node definitions to load actual classes
        actual_node_definitions = []
        for node_def in library_schema.nodes:
            candidate_path = Path(node_def.file_path)
            try:
                module = self._load_module_from_file(candidate_path, LibraryManager.SANDBOX_LIBRARY_NAME)
            except Exception as err:
                root_cause = self._get_root_cause_from_exception(err)
                problems.append(
                    NodeModuleImportProblem(
                        class_name=node_def.class_name,
                        file_path=str(candidate_path),
                        error_message=str(err),
                        root_cause=str(root_cause),
                    )
                )
                details = f"Attempted to load module in sandbox library '{candidate_path}'. Failed because an exception occurred: {err}."
                logger.warning(details)
                continue  # SKIP IT

            # Peek inside for any BaseNodes.
            for class_name, obj in vars(module).items():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseNode)
                    and type(obj) is not BaseNode
                    and obj.__module__ == module.__name__
                ):
                    details = f"Found node '{class_name}' in sandbox library '{candidate_path}'."
                    logger.debug(details)

                    # Get metadata from class attributes if they exist, otherwise use defaults
                    node_icon = getattr(obj, "ICON", "square-dashed")
                    node_description = getattr(
                        obj, "DESCRIPTION", f"'{class_name}' (loaded from the {LibraryManager.SANDBOX_LIBRARY_NAME})."
                    )
                    node_color = getattr(obj, "COLOR", None)

                    node_metadata = NodeMetadata(
                        category="Griptape Nodes Sandbox",
                        description=node_description,
                        display_name=class_name,
                        icon=node_icon,
                        color=node_color,
                    )
                    node_definition = NodeDefinition(
                        class_name=class_name,
                        file_path=str(candidate_path),
                        metadata=node_metadata,
                    )
                    actual_node_definitions.append(node_definition)

        if not actual_node_definitions:
            logger.info("No nodes found in sandbox library '%s'. Skipping.", sandbox_library_dir)
            return

        # Use the existing schema but replace nodes with actual discovered ones
        library_data = LibrarySchema(
            name=library_schema.name,
            library_schema_version=library_schema.library_schema_version,
            metadata=library_schema.metadata,
            categories=library_schema.categories,
            nodes=actual_node_definitions,
        )

        # Register the library.
        # Create or get the library
        try:
            # Try to create a new library
            library = LibraryRegistry.generate_new_library(
                library_data=library_data,
                mark_as_default_library=True,
            )

        except KeyError as err:
            # Library already exists
            self._library_file_path_to_info[sandbox_library_dir_as_posix] = LibraryManager.LibraryInfo(
                lifecycle_state=LibraryLifecycleState.FAILURE,
                library_path=sandbox_library_dir_as_posix,
                library_name=library_data.name,
                library_version=library_data.metadata.library_version,
                fitness=LibraryFitness.UNUSABLE,
                problems=[DuplicateLibraryProblem()],
            )

            details = f"Attempted to load Library JSON file from '{sandbox_library_dir}'. Failed because a Library '{library_data.name}' already exists. Error: {err}."
            logger.error(details)
            return

        # Load nodes into the library
        library_load_results = await asyncio.to_thread(
            self._attempt_load_nodes_from_library,
            library_data=library_data,
            library=library,
            base_dir=sandbox_library_dir,
            library_file_path=sandbox_library_dir_as_posix,
            library_version=library_data.metadata.library_version,
            problems=problems,
        )
        self._library_file_path_to_info[sandbox_library_dir_as_posix] = library_load_results

    def _find_files_in_dir(self, directory: Path, extension: str) -> list[Path]:
        """Find all files with given extension in directory, excluding common non-source directories."""
        ret_val = []
        for root, dirs, files_found in os.walk(directory):
            # Modify dirs in-place to skip excluded directories
            # Also skip any directory starting with '.'
            dirs[:] = [d for d in dirs if d not in EXCLUDED_SCAN_DIRECTORIES and not d.startswith(".")]

            for file in files_found:
                if file.endswith(extension):
                    file_path = Path(root) / file
                    ret_val.append(file_path)
        return ret_val

    def _remove_missing_libraries_from_config(self, config_category: str) -> None:
        # Now remove all libraries that were missing from the user's config.
        config_mgr = GriptapeNodes.ConfigManager()
        libraries_to_register_category = config_mgr.get_config_value(config_category)

        paths_to_remove = set()
        for library_path, library_info in self._library_file_path_to_info.items():
            if library_info.fitness == LibraryFitness.MISSING:
                # Remove this file path from the config.
                paths_to_remove.add(library_path.lower())

        if paths_to_remove and libraries_to_register_category:
            libraries_to_register_category = [
                library for library in libraries_to_register_category if library.lower() not in paths_to_remove
            ]
            config_mgr.set_config_value(config_category, libraries_to_register_category)

    def _migrate_old_xdg_library_paths(self) -> None:
        """Automatically removes old XDG library paths and adds git URLs to download list.

        This method removes library paths that were stored in the old XDG data home location
        (~/.local/share/griptape_nodes/libraries/) from the libraries_to_register configuration,
        and automatically adds the corresponding git URLs to libraries_to_download to ensure
        the libraries are re-downloaded. This migration happens automatically on app startup,
        so users don't need to run gtn init.
        """
        config_mgr = GriptapeNodes.ConfigManager()

        # Get both config lists
        register_key = LIBRARIES_TO_REGISTER_KEY
        download_key = LIBRARIES_TO_DOWNLOAD_KEY

        libraries_to_register = config_mgr.get_config_value(register_key)
        libraries_to_download = config_mgr.get_config_value(download_key) or []

        if not libraries_to_register:
            return

        # Filter and get which libraries were removed
        filtered_libraries, removed_library_names = filter_old_xdg_library_paths(libraries_to_register)

        # If any paths were removed
        paths_removed = len(libraries_to_register) - len(filtered_libraries)
        if paths_removed > 0:
            # Update libraries_to_register
            config_mgr.set_config_value(register_key, filtered_libraries)

            # Add corresponding git URLs to libraries_to_download
            updated_downloads = self._add_git_urls_for_removed_libraries(
                libraries_to_download,
                removed_library_names,
            )

            urls_added = len(updated_downloads) - len(libraries_to_download)
            if urls_added > 0:
                config_mgr.set_config_value(download_key, updated_downloads)

            logger.info(
                "Automatically migrated library configuration: removed %d old XDG path(s), added %d git URL(s) to download",
                paths_removed,
                urls_added,
            )

    def _add_git_urls_for_removed_libraries(
        self,
        current_downloads: list[str],
        removed_library_names: set[str],
    ) -> list[str]:
        """Add git URLs for removed libraries if not already present.

        Args:
            current_downloads: Current list of git URLs in libraries_to_download
            removed_library_names: Set of library names that were removed (e.g., "griptape_nodes_library")

        Returns:
            Updated list with new git URLs added (deduplicated)
        """
        if not removed_library_names:
            return current_downloads

        # Get current repository names for deduplication
        current_repo_names = {extract_repo_name_from_url(url) for url in current_downloads}

        new_downloads = current_downloads.copy()

        for lib_name in removed_library_names:
            if lib_name not in LIBRARY_GIT_URLS:
                continue

            git_url = LIBRARY_GIT_URLS[lib_name]
            repo_name = extract_repo_name_from_url(git_url)

            # Only add if not already present
            if repo_name not in current_repo_names:
                new_downloads.append(git_url)
                current_repo_names.add(repo_name)

        return new_downloads

    async def reload_libraries_request(self, request: ReloadAllLibrariesRequest) -> ResultPayload:  # noqa: ARG002
        # Start with a clean slate.
        clear_all_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
        clear_all_result = await GriptapeNodes.ahandle_request(clear_all_request)
        if not clear_all_result.succeeded():
            details = "Failed to clear the existing object state when preparing to reload all libraries."
            return ReloadAllLibrariesResultFailure(result_details=details)

        # Unload all libraries now.
        all_libraries_request = ListRegisteredLibrariesRequest()
        all_libraries_result = GriptapeNodes.handle_request(all_libraries_request)
        if not isinstance(all_libraries_result, ListRegisteredLibrariesResultSuccess):
            details = "When preparing to reload all libraries, failed to get registered libraries."
            logger.error(details)
            return ReloadAllLibrariesResultFailure(result_details=details)

        for library_name in all_libraries_result.libraries:
            unload_library_request = UnloadLibraryFromRegistryRequest(library_name=library_name)
            unload_library_result = GriptapeNodes.handle_request(unload_library_request)
            if not unload_library_result.succeeded():
                details = f"When preparing to reload all libraries, failed to unload library '{library_name}'."
                logger.error(details)
                return ReloadAllLibrariesResultFailure(result_details=details)

        # Load (or reload, which should trigger a hot reload) all libraries
        await self.load_all_libraries_from_config()

        details = (
            "Successfully reloaded all libraries. All object state was cleared and previous libraries were unloaded."
        )
        return ReloadAllLibrariesResultSuccess(result_details=ResultDetails(message=details, level=logging.INFO))

    def discover_libraries_request(
        self,
        request: DiscoverLibrariesRequest,  # noqa: ARG002
    ) -> DiscoverLibrariesResultSuccess | DiscoverLibrariesResultFailure:
        """Discover libraries from config and track them in discovered state.

        This is the event handler for DiscoverLibrariesRequest.
        Scans configured library paths and creates LibraryInfo entries in DISCOVERED state.
        """
        try:
            discovered_paths = set(self._discover_library_files())
        except Exception as e:
            logger.exception("Failed to discover library files")
            return DiscoverLibrariesResultFailure(
                result_details=f"Failed to discover library files: {e}",
            )

        # Create minimal LibraryInfo entries for libraries not yet tracked
        for file_path in discovered_paths:
            file_path_str = str(file_path)

            # Skip if already tracked (regardless of lifecycle state)
            if file_path_str in self._library_file_path_to_info:
                continue

            # Create minimal LibraryInfo entry in discovered state
            self._library_file_path_to_info[file_path_str] = LibraryManager.LibraryInfo(
                lifecycle_state=LibraryLifecycleState.DISCOVERED,
                fitness=LibraryFitness.NOT_EVALUATED,
                library_path=file_path_str,
                library_name=None,
                library_version=None,
            )

        # Success path at the end
        return DiscoverLibrariesResultSuccess(
            result_details=ResultDetails(message=f"Discovered {len(discovered_paths)} libraries"),
            libraries_discovered=discovered_paths,
        )

    def evaluate_library_fitness_request(
        self, request: EvaluateLibraryFitnessRequest
    ) -> EvaluateLibraryFitnessResultSuccess | EvaluateLibraryFitnessResultFailure:
        """Evaluate library fitness using version compatibility checks.

        Extracts version checking logic from _attempt_load_nodes_from_library.
        Checks engine version compatibility without loading Python modules.
        """
        schema = request.schema
        problems: list[LibraryProblem] = []

        # Check for version-based compatibility issues
        version_issues = GriptapeNodes.VersionCompatibilityManager().check_library_version_compatibility(schema)
        has_disqualifying_issues = False

        for issue in version_issues:
            problems.append(issue.problem)
            if issue.severity == LibraryFitness.UNUSABLE:
                has_disqualifying_issues = True

        if has_disqualifying_issues:
            return EvaluateLibraryFitnessResultFailure(
                result_details=f"Library '{schema.name}' has version compatibility issues",
                fitness=LibraryFitness.UNUSABLE,
                problems=problems,
            )

        # Determine fitness based on whether we have any non-disqualifying issues
        fitness = LibraryFitness.FLAWED if problems else LibraryFitness.GOOD

        return EvaluateLibraryFitnessResultSuccess(
            result_details=ResultDetails(message=f"Library '{schema.name}' is compatible"),
            fitness=fitness,
            problems=problems,
        )

    async def load_library_request(  # noqa: PLR0912, PLR0915, C901, PLR0911
        self, request: LoadLibraryRequest
    ) -> LoadLibraryResultSuccess | LoadLibraryResultFailure:
        """Load a single library by name, progressing through all lifecycle phases.

        Args:
            request: LoadLibraryRequest containing library_name and perform_discovery_if_not_found

        Returns:
            LoadLibraryResultSuccess if loaded, LoadLibraryResultFailure otherwise
        """
        library_name = request.library_name

        # Check if already loaded in registry
        try:
            LibraryRegistry.get_library(name=library_name)
        except KeyError:
            # Library not in registry, continue with loading
            pass
        else:
            # Library exists in registry
            library_info = self.get_library_info_by_library_name(library_name)
            if library_info is None:
                details = f"Library '{library_name}' is in registry but LibraryInfo is missing"
                return LoadLibraryResultFailure(
                    result_details=ResultDetails(message=details, level=logging.ERROR),
                    failure_phase=LibraryLifecycleState.FAILURE,
                    library_info=None,
                )

            # Already loaded and good to go.
            return LoadLibraryResultSuccess(
                result_details=ResultDetails(message=f"Library '{library_name}' already loaded"),
                library_info=library_info,
                was_already_loaded=True,
            )

        # Check if library info exists
        library_info = self.get_library_info_by_library_name(library_name)

        # If not found and discovery is allowed, try discovery
        if library_info is None and request.perform_discovery_if_not_found:
            discover_result = self.discover_libraries_request(DiscoverLibrariesRequest())
            if isinstance(discover_result, DiscoverLibrariesResultSuccess):
                library_info = self.get_library_info_by_library_name(library_name)

        # If still not found, fail
        if library_info is None:
            details = f"Library '{library_name}' not found"
            if request.perform_discovery_if_not_found:
                details += " (discovery was attempted)"
            return LoadLibraryResultFailure(
                result_details=ResultDetails(message=details, level=logging.ERROR),
                failure_phase=LibraryLifecycleState.FAILURE,
                library_info=None,
            )

        # Progress through lifecycle phases until reaching a terminal state
        while True:
            current_state = library_info.lifecycle_state

            match current_state:
                case LibraryLifecycleState.LOADED:
                    # Terminal state: inconsistent (marked LOADED but not in registry)
                    details = f"Library '{library_name}' marked as LOADED but not in registry"
                    # Write library_info to dict to track the broken library and what's wrong with it
                    self._library_file_path_to_info[library_info.library_path] = library_info
                    return LoadLibraryResultFailure(
                        result_details=ResultDetails(message=details, level=logging.ERROR),
                        failure_phase=LibraryLifecycleState.FAILURE,
                        library_info=library_info,
                    )

                case LibraryLifecycleState.FAILURE:
                    # Terminal state: failure
                    details = f"Library '{library_name}' is in FAILURE state and cannot be loaded"
                    # Write library_info to dict to track the broken library and what's wrong with it
                    self._library_file_path_to_info[library_info.library_path] = library_info
                    return LoadLibraryResultFailure(
                        result_details=ResultDetails(message=details, level=logging.ERROR),
                        failure_phase=LibraryLifecycleState.FAILURE,
                        library_info=library_info,
                    )

                case LibraryLifecycleState.DISCOVERED:
                    # DISCOVERED → METADATA_LOADED
                    metadata_result = self.load_library_metadata_from_file_request(
                        LoadLibraryMetadataFromFileRequest(file_path=library_info.library_path)
                    )
                    if isinstance(metadata_result, LoadLibraryMetadataFromFileResultFailure):
                        # Write library_info to dict to track the broken library and what's wrong with it
                        self._library_file_path_to_info[library_info.library_path] = library_info
                        return LoadLibraryResultFailure(
                            result_details=metadata_result.result_details,
                            failure_phase=LibraryLifecycleState.DISCOVERED,
                            library_info=library_info,
                        )

                    # Update local library_info with metadata results
                    library_info.library_name = metadata_result.library_schema.name
                    library_info.library_version = metadata_result.library_schema.metadata.library_version
                    library_info.lifecycle_state = LibraryLifecycleState.METADATA_LOADED

                case LibraryLifecycleState.METADATA_LOADED:
                    # METADATA_LOADED → EVALUATED
                    # Need to load schema to pass to evaluate request
                    metadata_result = self.load_library_metadata_from_file_request(
                        LoadLibraryMetadataFromFileRequest(file_path=library_info.library_path)
                    )
                    if isinstance(metadata_result, LoadLibraryMetadataFromFileResultFailure):
                        # Write library_info to dict to track the broken library and what's wrong with it
                        self._library_file_path_to_info[library_info.library_path] = library_info
                        return LoadLibraryResultFailure(
                            result_details=metadata_result.result_details,
                            failure_phase=LibraryLifecycleState.METADATA_LOADED,
                            library_info=library_info,
                        )

                    evaluate_result = self.evaluate_library_fitness_request(
                        EvaluateLibraryFitnessRequest(schema=metadata_result.library_schema)
                    )
                    if isinstance(evaluate_result, EvaluateLibraryFitnessResultFailure):
                        # Write library_info to dict to track the broken library and what's wrong with it
                        self._library_file_path_to_info[library_info.library_path] = library_info
                        return LoadLibraryResultFailure(
                            result_details=evaluate_result.result_details,
                            failure_phase=LibraryLifecycleState.METADATA_LOADED,
                            library_info=library_info,
                        )

                    # Update local library_info with evaluation results
                    library_info.fitness = evaluate_result.fitness
                    library_info.problems.extend(evaluate_result.problems)
                    library_info.lifecycle_state = LibraryLifecycleState.EVALUATED

                case LibraryLifecycleState.EVALUATED:
                    # EVALUATED → DEPENDENCIES_INSTALLED
                    install_result = await self.install_library_dependencies_request(
                        InstallLibraryDependenciesRequest(library_file_path=library_info.library_path)
                    )
                    if isinstance(install_result, InstallLibraryDependenciesResultFailure):
                        # Write library_info to dict to track the broken library and what's wrong with it
                        self._library_file_path_to_info[library_info.library_path] = library_info
                        return LoadLibraryResultFailure(
                            result_details=install_result.result_details,
                            failure_phase=LibraryLifecycleState.EVALUATED,
                            library_info=library_info,
                        )

                    # Update local library_info
                    library_info.lifecycle_state = LibraryLifecycleState.DEPENDENCIES_INSTALLED

                case LibraryLifecycleState.DEPENDENCIES_INSTALLED:
                    # DEPENDENCIES_INSTALLED → LOADED
                    # At this phase, we have schema/fitness/dependencies ready, just need to register
                    register_result = await self.register_library_from_file_request(
                        RegisterLibraryFromFileRequest(file_path=library_info.library_path)
                    )
                    if isinstance(register_result, RegisterLibraryFromFileResultFailure):
                        # Write library_info to dict to track the broken library and what's wrong with it
                        self._library_file_path_to_info[library_info.library_path] = library_info
                        return LoadLibraryResultFailure(
                            result_details=register_result.result_details,
                            failure_phase=LibraryLifecycleState.DEPENDENCIES_INSTALLED,
                            library_info=library_info,
                        )

                    # Update local library_info
                    library_info.lifecycle_state = LibraryLifecycleState.LOADED

                    # Exit loop after final phase
                    break

                case _:
                    # Unexpected state
                    msg = f"Library '{library_name}' in unexpected lifecycle state: {current_state}"
                    raise ValueError(msg)

        # Final verification: library should now be in registry
        try:
            LibraryRegistry.get_library(name=library_name)
        except KeyError:
            details = f"Library '{library_name}' completed all phases but not in registry"
            # Write library_info to dict to track the broken library and what's wrong with it
            self._library_file_path_to_info[library_info.library_path] = library_info
            return LoadLibraryResultFailure(
                result_details=ResultDetails(message=details, level=logging.ERROR),
                failure_phase=LibraryLifecycleState.LOADED,
                library_info=library_info,
            )

        # Write final library_info to dict (tracks successful load)
        self._library_file_path_to_info[library_info.library_path] = library_info

        return LoadLibraryResultSuccess(
            result_details=ResultDetails(message=f"Library '{library_name}' loaded successfully"),
            library_info=library_info,
            was_already_loaded=False,
        )

    async def load_libraries_request(self, request: LoadLibrariesRequest) -> ResultPayload:  # noqa: ARG002
        """Load all libraries from configuration (backward compatibility wrapper).

        This is the legacy entry point that loads all configured libraries.
        New code should use LoadLibraryRequest to load specific libraries instead.
        """
        # First, discover all available libraries
        discover_result = self.discover_libraries_request(DiscoverLibrariesRequest())
        if isinstance(discover_result, DiscoverLibrariesResultFailure):
            return LoadLibrariesResultFailure(result_details=f"Discovery failed: {discover_result.result_details}")

        # Get all library names from discovered libraries
        library_names = [
            library_info.library_name
            for library_info in self._library_file_path_to_info.values()
            if library_info.library_name
        ]

        if not library_names:
            details = "No libraries found in configuration."
            return LoadLibrariesResultSuccess(result_details=ResultDetails(message=details, level=logging.INFO))

        # Load each discovered library
        loaded_count = 0
        failed_libraries = []

        for library_name in library_names:
            load_result = await self.load_library_request(
                LoadLibraryRequest(library_name=library_name, perform_discovery_if_not_found=False)
            )

            if isinstance(load_result, LoadLibraryResultSuccess):
                if not load_result.was_already_loaded:
                    loaded_count += 1
            else:
                failed_libraries.append(library_name)
                logger.warning("Failed to load library '%s': %s", library_name, load_result.result_details)

        if loaded_count == 0 and len(failed_libraries) > 0:
            return LoadLibrariesResultFailure(
                result_details=f"Failed to load any libraries. Failed: {', '.join(failed_libraries)}"
            )

        message = f"Loaded {loaded_count} libraries"
        if failed_libraries:
            message += f". Failed: {', '.join(failed_libraries)}"

        return LoadLibrariesResultSuccess(result_details=ResultDetails(message=message, level=logging.INFO))

    def _discover_library_files(self) -> list[Path]:
        """Discover library JSON files from config and workspace recursively.

        Returns:
            List of library file paths found
        """
        config_mgr = GriptapeNodes.ConfigManager()
        user_libraries_section = LIBRARIES_TO_REGISTER_KEY

        discovered_libraries = set()

        def process_path(path: Path) -> None:
            """Process a path, handling both files and directories."""
            if path.is_dir():
                # Process all library JSON files recursively in the directory
                discovered_libraries.update(path.rglob(LibraryManager.LIBRARY_CONFIG_GLOB_PATTERN))
            elif path.suffix == ".json":
                discovered_libraries.add(path)

        # Add from config
        config_libraries = config_mgr.get_config_value(user_libraries_section, default=[])
        for library_path_str in config_libraries:
            # Filter out falsy values that will resolve to current directory
            if library_path_str:
                library_path = Path(library_path_str)
                if library_path.exists():
                    process_path(library_path)

        return list(discovered_libraries)

    async def check_library_update_request(self, request: CheckLibraryUpdateRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915
        """Check if a library has updates available via git."""
        library_name = request.library_name

        # Check if the library exists
        try:
            library = LibraryRegistry.get_library(name=library_name)
        except KeyError:
            details = f"Attempted to check for updates for Library '{library_name}'. Failed because no Library with that name was registered."
            return CheckLibraryUpdateResultFailure(result_details=details)

        # Find the library file path
        library_file_path = None
        for file_path, library_info in self._library_file_path_to_info.items():
            if library_info.library_name == library_name:
                library_file_path = file_path
                break

        if library_file_path is None:
            details = f"Attempted to check for updates for Library '{library_name}'. Failed because no file path could be found for this library."
            return CheckLibraryUpdateResultFailure(result_details=details)

        # Get the library directory (parent of the JSON file)
        library_dir = Path(library_file_path).parent.absolute()

        # Check if library is in a monorepo (multiple libraries in same git repository)
        if await asyncio.to_thread(is_monorepo, library_dir):
            details = (
                f"Library '{library_name}' is in a monorepo with multiple libraries. Updates must be managed manually."
            )
            logger.info(details)
            # Get git info for the response
            git_remote = await asyncio.to_thread(get_git_remote, library_dir)
            git_ref = await asyncio.to_thread(get_current_ref, library_dir)
            current_version = library.get_metadata().library_version
            return CheckLibraryUpdateResultSuccess(
                has_update=False,
                current_version=current_version,
                latest_version=current_version,
                git_remote=git_remote,
                git_ref=git_ref,
                local_commit=None,
                remote_commit=None,
                result_details=details,
            )

        # Check if the library directory is a git repository and get remote URL and ref
        try:
            git_remote = await asyncio.to_thread(get_git_remote, library_dir)
            if git_remote is None:
                details = f"Library '{library_name}' is not a git repository or has no remote configured."
                return CheckLibraryUpdateResultFailure(result_details=details)
        except GitRemoteError as e:
            details = f"Failed to get git remote for Library '{library_name}': {e}"
            return CheckLibraryUpdateResultFailure(result_details=details)

        try:
            git_ref = await asyncio.to_thread(get_current_ref, library_dir)
        except GitRefError as e:
            details = f"Failed to get current git reference for Library '{library_name}': {e}"
            return CheckLibraryUpdateResultFailure(result_details=details)

        # Get current library version
        current_version = library.get_metadata().library_version
        if current_version is None:
            details = f"Library '{library_name}' has no version information."
            return CheckLibraryUpdateResultFailure(result_details=details)

        # Get local commit SHA
        local_commit = await asyncio.to_thread(get_local_commit_sha, library_dir)

        # Clone remote and get latest version and commit SHA (using current ref or HEAD if detached)
        try:
            ref_to_check = git_ref or "HEAD"
            version_info = await asyncio.to_thread(clone_and_get_library_version, git_remote, ref_to_check)
            latest_version = version_info.library_version
            remote_commit = version_info.commit_sha
        except GitCloneError as e:
            details = f"Failed to retrieve latest version from git remote for Library '{library_name}': {e}"
            return CheckLibraryUpdateResultFailure(result_details=details)

        # Determine if update is available using version comparison and commit comparison
        try:
            current_ver = Version.parse(current_version)
            latest_ver = Version.parse(latest_version)

            # Update detection logic:
            # 1. If remote version > local version -> update available (semantic versioning)
            if latest_ver > current_ver:
                has_update = True
                update_reason = "version increased"
            # 2. If remote version < local version -> no update (prevent regression)
            elif latest_ver < current_ver:
                has_update = False
                update_reason = "version decreased (regression blocked)"
            # 3. If versions equal -> check commits
            elif local_commit is not None and remote_commit is not None and local_commit != remote_commit:
                has_update = True
                update_reason = "commits differ (same version)"
            else:
                has_update = False
                update_reason = "versions and commits match"

        except ValueError as e:
            details = f"Failed to parse version strings for Library '{library_name}': {e}"
            return CheckLibraryUpdateResultFailure(result_details=details)

        details = f"Successfully checked for updates for Library '{library_name}'. Current version: {current_version}, Latest version: {latest_version}, Has update: {has_update} ({update_reason})"
        logger.info(details)

        return CheckLibraryUpdateResultSuccess(
            has_update=has_update,
            current_version=current_version,
            latest_version=latest_version,
            git_remote=git_remote,
            git_ref=git_ref,
            local_commit=local_commit,
            remote_commit=remote_commit,
            result_details=details,
        )

    async def _validate_and_prepare_library_for_git_operation(
        self,
        library_name: str,
        failure_result_class: type[ResultPayloadFailure],
        operation_description: str,
    ) -> LibraryGitOperationContext | ResultPayloadFailure:
        """Validate library exists and prepare for git operation.

        Args:
            library_name: Name of the library to validate
            failure_result_class: Class to use for failure results (e.g., UpdateLibraryResultFailure)
            operation_description: Description of operation for error messages (e.g., "update", "switch branch/tag for")

        Returns:
            On success: LibraryGitOperationContext with library info
            On failure: ResultPayloadFailure instance
        """
        # Check if the library exists
        try:
            library = LibraryRegistry.get_library(name=library_name)
        except KeyError:
            details = f"Attempted to {operation_description} Library '{library_name}'. Failed because no Library with that name was registered."
            return failure_result_class(result_details=details)

        # Get current version
        old_version = library.get_metadata().library_version
        if old_version is None:
            details = f"Library '{library_name}' has no version information."
            return failure_result_class(result_details=details)

        # Find the library file path
        library_file_path = None
        for file_path, library_info in self._library_file_path_to_info.items():
            if library_info.library_name == library_name:
                library_file_path = file_path
                break

        if library_file_path is None:
            details = f"Attempted to {operation_description} Library '{library_name}'. Failed because no file path could be found for this library."
            return failure_result_class(result_details=details)

        # Get the library directory (parent of the JSON file)
        library_dir = Path(library_file_path).parent.absolute()

        return LibraryGitOperationContext(
            library=library,
            old_version=old_version,
            library_file_path=library_file_path,
            library_dir=library_dir,
        )

    async def _reload_library_after_git_operation(
        self,
        library_name: str,
        library_file_path: str,
        *,
        failure_result_class: type[ResultPayloadFailure],
    ) -> str | ResultPayloadFailure:
        """Reload library after git operation.

        Args:
            library_name: Name of the library to reload
            library_file_path: Path to the library JSON file
            failure_result_class: Class to use for failure results

        Returns:
            On success: new_version (str, may be "unknown")
            On failure: ResultPayloadFailure instance
        """
        # Unload the library
        unload_result = GriptapeNodes.handle_request(UnloadLibraryFromRegistryRequest(library_name=library_name))
        if not unload_result.succeeded():
            details = f"Failed to unload Library '{library_name}' after git operation."
            return failure_result_class(result_details=details)

        # Search for the library JSON file using flexible pattern to handle filename variations
        # (after git operations, the filename might change between griptape-nodes-library.json and griptape_nodes_library.json)
        library_dir = Path(library_file_path).parent
        actual_library_file = find_file_in_directory(library_dir, "griptape[-_]nodes[-_]library.json")

        if actual_library_file is None:
            details = (
                f"Failed to find library JSON file in {library_dir} after git operation for Library '{library_name}'."
            )
            return failure_result_class(result_details=details)

        # Use the found file path for reloading
        actual_library_file_path = str(actual_library_file)

        # Reload the library from file
        reload_result = await GriptapeNodes.ahandle_request(
            RegisterLibraryFromFileRequest(file_path=actual_library_file_path)
        )
        if not isinstance(reload_result, RegisterLibraryFromFileResultSuccess):
            details = f"Failed to reload Library '{library_name}' after git operation."
            return failure_result_class(result_details=details)

        # Get new version after reload
        try:
            updated_library = LibraryRegistry.get_library(name=library_name)
            new_version = updated_library.get_metadata().library_version
            if new_version is None:
                new_version = "unknown"
        except KeyError:
            new_version = "unknown"

        return new_version

    async def update_library_request(self, request: UpdateLibraryRequest) -> ResultPayload:
        """Update a library to the latest version using the appropriate git strategy.

        Automatically detects whether the library uses branch-based or tag-based workflow:
        - Branch-based: Uses git fetch + git reset --hard (forces local to match remote)
        - Tag-based: Uses git fetch --tags --force + git checkout
        """
        library_name = request.library_name

        # Validate library and prepare for git operation
        validation_result = await self._validate_and_prepare_library_for_git_operation(
            library_name=library_name,
            failure_result_class=UpdateLibraryResultFailure,
            operation_description="update",
        )
        if isinstance(validation_result, ResultPayloadFailure):
            return validation_result

        old_version = validation_result.old_version
        library_file_path = validation_result.library_file_path
        library_dir = validation_result.library_dir

        # Check if library is in a monorepo (multiple libraries in same git repository)
        if await asyncio.to_thread(is_monorepo, library_dir):
            details = f"Cannot update Library '{library_name}'. Repository contains multiple libraries and must be updated manually."
            return UpdateLibraryResultFailure(result_details=details)

        # Perform git update (auto-detects branch vs tag workflow)
        try:
            await asyncio.to_thread(
                update_library_git,
                library_dir,
                overwrite_existing=request.overwrite_existing,
            )
        except (GitPullError, GitRepositoryError) as e:
            error_msg = str(e).lower()

            # Check if error is retryable (uncommitted changes)
            retryable = "uncommitted changes" in error_msg or "unstaged changes" in error_msg

            details = f"Failed to update Library '{library_name}': {e}"
            return UpdateLibraryResultFailure(result_details=details, retryable=retryable)

        # Reload library
        reload_result = await self._reload_library_after_git_operation(
            library_name=library_name,
            library_file_path=library_file_path,
            failure_result_class=UpdateLibraryResultFailure,
        )
        if isinstance(reload_result, ResultPayloadFailure):
            return reload_result

        new_version = reload_result

        details = f"Successfully updated Library '{library_name}' from version {old_version} to {new_version}."
        return UpdateLibraryResultSuccess(
            old_version=old_version,
            new_version=new_version,
            result_details=details,
        )

    async def switch_library_ref_request(self, request: SwitchLibraryRefRequest) -> ResultPayload:
        """Switch a library to a different git branch or tag."""
        library_name = request.library_name
        ref_name = request.ref_name

        # Validate library and prepare for git operation
        validation_result = await self._validate_and_prepare_library_for_git_operation(
            library_name=library_name,
            failure_result_class=SwitchLibraryRefResultFailure,
            operation_description="switch branch/tag for",
        )
        if isinstance(validation_result, ResultPayloadFailure):
            return validation_result

        old_version = validation_result.old_version
        library_file_path = validation_result.library_file_path
        library_dir = validation_result.library_dir

        # Get current ref (branch or tag) before switch
        try:
            old_ref = await asyncio.to_thread(get_current_ref, library_dir)
            if old_ref is None:
                details = f"Library '{library_name}' is not on a branch/tag or is not a git repository."
                return SwitchLibraryRefResultFailure(result_details=details)
        except GitRefError as e:
            details = f"Failed to get current branch/tag for Library '{library_name}': {e}"
            return SwitchLibraryRefResultFailure(result_details=details)

        # Perform git ref switch (branch or tag)
        try:
            await asyncio.to_thread(switch_branch_or_tag, library_dir, ref_name)
        except (GitRefError, GitRepositoryError) as e:
            details = f"Failed to switch to '{ref_name}' for Library '{library_name}': {e}"
            return SwitchLibraryRefResultFailure(result_details=details)

        # Reload library
        reload_result = await self._reload_library_after_git_operation(
            library_name=library_name,
            library_file_path=library_file_path,
            failure_result_class=SwitchLibraryRefResultFailure,
        )
        if isinstance(reload_result, ResultPayloadFailure):
            return reload_result

        new_version = reload_result

        # Get new ref (branch or tag) after switch
        try:
            new_ref = await asyncio.to_thread(get_current_ref, library_dir)
            if new_ref is None:
                new_ref = "unknown"
        except GitRefError:
            new_ref = "unknown"

        details = f"Successfully switched Library '{library_name}' from '{old_ref}' (version {old_version}) to '{new_ref}' (version {new_version})."
        return SwitchLibraryRefResultSuccess(
            old_ref=old_ref,
            new_ref=new_ref,
            old_version=old_version,
            new_version=new_version,
            result_details=details,
        )

    async def download_library_request(self, request: DownloadLibraryRequest) -> ResultPayload:  # noqa: PLR0911, PLR0912, PLR0915, C901
        """Download a library from a git repository."""
        git_url = request.git_url
        branch_tag_commit = request.branch_tag_commit
        target_directory_name = request.target_directory_name
        download_directory = request.download_directory

        # Determine the parent directory for the download
        config_mgr = GriptapeNodes.ConfigManager()

        if download_directory is not None:
            # Use custom download directory if provided
            libraries_path = Path(download_directory)
        else:
            # Use default from config
            libraries_dir_setting = config_mgr.get_config_value("libraries_directory")
            if not libraries_dir_setting:
                details = "Cannot download library: libraries_directory setting is not configured."
                return DownloadLibraryResultFailure(result_details=details)
            libraries_path = config_mgr.workspace_path / libraries_dir_setting

        # Ensure parent directory exists
        libraries_path.mkdir(parents=True, exist_ok=True)

        # Determine target directory name
        if target_directory_name is None:
            # Extract from git URL (e.g., "https://github.com/user/repo.git" -> "repo")
            target_directory_name = git_url.rstrip("/").split("/")[-1]
            target_directory_name = target_directory_name.removesuffix(".git")

        # Construct full target path
        target_path = libraries_path / target_directory_name

        # Check if target directory already exists
        skip_clone = False
        if target_path.exists():
            if request.overwrite_existing:
                # Delete existing directory before cloning
                delete_request = DeleteFileRequest(path=str(target_path), workspace_only=False)
                delete_result = await GriptapeNodes.ahandle_request(delete_request)

                if isinstance(delete_result, DeleteFileResultFailure):
                    details = f"Cannot delete existing directory at {target_path}: {delete_result.result_details}"
                    return DownloadLibraryResultFailure(result_details=details)

                logger.info("Deleted existing directory at %s for overwrite", target_path)
            else:
                # Check fail_on_exists flag
                if request.fail_on_exists:
                    # Fail with retryable error for interactive CLI
                    details = f"Cannot download library: target directory already exists at {target_path}"
                    return DownloadLibraryResultFailure(result_details=details, retryable=True)

                # Skip cloning since directory already exists, but continue with registration
                skip_clone = True
                logger.debug(
                    "Library directory already exists at %s, skipping download but will proceed with registration",
                    target_path,
                )

        # Clone the repository (unless skipping because it already exists)
        if skip_clone:
            logger.debug("Using existing library directory at %s", target_path)
        else:
            try:
                await asyncio.to_thread(clone_repository, git_url, target_path, branch_tag_commit)
            except GitCloneError as e:
                details = f"Failed to clone repository from {git_url} to {target_path}: {e}"
                return DownloadLibraryResultFailure(result_details=details)

        # Recursively search for griptape_nodes_library.json file
        library_json_path = find_file_in_directory(target_path, "griptape[-_]nodes[-_]library.json")
        if library_json_path is None:
            details = f"Downloaded library from {git_url} but no library JSON file found in {target_path}"
            return DownloadLibraryResultFailure(result_details=details)

        try:
            with library_json_path.open() as f:
                library_data = json.load(f)
        except json.JSONDecodeError as e:
            details = f"Failed to parse griptape_nodes_library.json from downloaded library: {e}"
            return DownloadLibraryResultFailure(result_details=details)

        # Extract library name
        library_name = library_data.get("name")
        if library_name is None:
            details = "Downloaded library has no 'name' field in griptape_nodes_library.json"
            return DownloadLibraryResultFailure(result_details=details)

        # Automatically register the downloaded library (unless disabled for startup downloads)
        if request.auto_register:
            register_request = RegisterLibraryFromFileRequest(file_path=str(library_json_path))
            register_result = await GriptapeNodes.ahandle_request(register_request)
            if not register_result.succeeded():
                logger.warning(
                    "Library '%s' was downloaded but registration failed: %s",
                    library_name,
                    register_result.result_details,
                )
            else:
                logger.info("Library '%s' registered successfully", library_name)

        # Add library JSON file path to config so it's registered on future startups
        libraries_to_register = config_mgr.get_config_value(LIBRARIES_TO_REGISTER_KEY, default=[])
        library_json_str = str(library_json_path)
        if library_json_str not in libraries_to_register:
            libraries_to_register.append(library_json_str)
            config_mgr.set_config_value(LIBRARIES_TO_REGISTER_KEY, libraries_to_register)
            logger.info("Added library '%s' to config for auto-registration on startup", library_name)

        if skip_clone:
            details = f"Library '{library_name}' already exists at {target_path} and has been registered"
        else:
            details = f"Successfully downloaded library '{library_name}' from {git_url} to {target_path}"
        return DownloadLibraryResultSuccess(
            library_name=library_name,
            library_path=str(library_json_path),
            result_details=details,
        )

    async def install_library_dependencies_request(self, request: InstallLibraryDependenciesRequest) -> ResultPayload:  # noqa: PLR0911
        """Install dependencies for a library."""
        library_file_path = request.library_file_path

        # Load library metadata from file
        metadata_request = LoadLibraryMetadataFromFileRequest(file_path=library_file_path)
        metadata_result = self.load_library_metadata_from_file_request(metadata_request)

        if not isinstance(metadata_result, LoadLibraryMetadataFromFileResultSuccess):
            details = f"Failed to load library metadata from {library_file_path}: {metadata_result.result_details}"
            return InstallLibraryDependenciesResultFailure(result_details=details)

        library_data = metadata_result.library_schema
        library_name = library_data.name
        library_metadata = library_data.metadata

        if not library_metadata.dependencies or not library_metadata.dependencies.pip_dependencies:
            details = f"Library '{library_name}' has no dependencies to install"
            logger.info(details)
            return InstallLibraryDependenciesResultSuccess(
                library_name=library_name, dependencies_installed=0, result_details=details
            )

        pip_dependencies = library_metadata.dependencies.pip_dependencies
        pip_install_flags = library_metadata.dependencies.pip_install_flags or []

        # Get venv path and initialize it
        venv_path = self._get_library_venv_path(library_name, library_file_path)

        try:
            library_venv_python_path = await self._init_library_venv(venv_path)
        except RuntimeError as e:
            details = f"Failed to initialize venv for library '{library_name}': {e}"
            return InstallLibraryDependenciesResultFailure(result_details=details)

        if not self._can_write_to_venv_location(library_venv_python_path):
            details = f"Venv location for library '{library_name}' at {venv_path} is not writable"
            logger.warning(details)
            return InstallLibraryDependenciesResultFailure(result_details=details)

        # Check disk space
        config_manager = GriptapeNodes.ConfigManager()
        min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_libraries")
        if not OSManager.check_available_disk_space(Path(venv_path), min_space_gb):
            error_msg = OSManager.format_disk_space_error(Path(venv_path))
            details = f"Insufficient disk space for dependencies (requires {min_space_gb} GB) for library '{library_name}': {error_msg}"
            return InstallLibraryDependenciesResultFailure(result_details=details)

        # Install dependencies
        logger.info("Installing %d dependencies for library '%s'", len(pip_dependencies), library_name)
        is_debug = config_manager.get_config_value("log_level").upper() == "DEBUG"

        try:
            await subprocess_run(
                [
                    sys.executable,
                    "-m",
                    "uv",
                    "pip",
                    "install",
                    *pip_dependencies,
                    *pip_install_flags,
                    "--python",
                    str(library_venv_python_path),
                ],
                check=True,
                capture_output=not is_debug,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            details = f"Failed to install dependencies for library '{library_name}': return code={e.returncode}, stderr={e.stderr}"
            return InstallLibraryDependenciesResultFailure(result_details=details)

        details = f"Successfully installed {len(pip_dependencies)} dependencies for library '{library_name}'"
        logger.info(details)
        return InstallLibraryDependenciesResultSuccess(
            library_name=library_name, dependencies_installed=len(pip_dependencies), result_details=details
        )

    async def sync_libraries_request(self, request: SyncLibrariesRequest) -> ResultPayload:  # noqa: C901, PLR0915
        """Sync all libraries to latest versions and ensure dependencies are installed."""
        # Phase 1: Download missing libraries from both config keys
        config_mgr = GriptapeNodes.ConfigManager()

        # Collect git URLs from both config keys
        download_config = config_mgr.get_config_value(LIBRARIES_TO_DOWNLOAD_KEY, default=[])
        register_config = config_mgr.get_config_value(LIBRARIES_TO_REGISTER_KEY, default=[])
        git_urls_from_register = [entry for entry in register_config if is_git_url(entry)]

        # Combine and deduplicate
        all_git_urls = list(set(download_config + git_urls_from_register))

        # Use shared download method
        update_summary = {}
        libraries_downloaded = 0

        if all_git_urls:
            logger.info("Found %d git URLs, downloading missing libraries", len(all_git_urls))
            download_results = await self._download_libraries_from_git_urls(all_git_urls)

            # Process results for summary
            for git_url, result in download_results.items():
                if result["success"]:
                    libraries_downloaded += 1
                    update_summary[result["library_name"]] = {
                        "status": "downloaded",
                        "git_url": git_url,
                    }
                elif result.get("error"):
                    logger.warning("Download failed for '%s': %s", git_url, result["error"])

        logger.info("Downloaded %d new libraries", libraries_downloaded)

        # Phase 2: Load libraries to ensure newly downloaded ones are registered
        logger.info("Loading libraries to register newly downloaded ones")
        load_request = LoadLibrariesRequest()
        load_result = await GriptapeNodes.ahandle_request(load_request)

        if not isinstance(load_result, LoadLibrariesResultSuccess):
            logger.warning("Failed to load libraries after download: %s", load_result.result_details)
            # Continue anyway - we can still update previously registered libraries

        # Phase 3: Check and update all registered libraries
        # Get all registered libraries
        list_result = await GriptapeNodes.ahandle_request(ListRegisteredLibrariesRequest())
        if not isinstance(list_result, ListRegisteredLibrariesResultSuccess):
            details = "Failed to list registered libraries for sync"
            return SyncLibrariesResultFailure(result_details=details)

        libraries_to_check = list_result.libraries

        logger.info("Checking %d registered libraries for updates", len(libraries_to_check))

        # Check all libraries for updates concurrently using task group
        async def check_library_for_update(library_name: str) -> tuple[str, ResultPayload]:
            """Check a single library for updates."""
            logger.info("Checking library '%s' for updates", library_name)
            check_result = await GriptapeNodes.ahandle_request(
                CheckLibraryUpdateRequest(library_name=library_name, failure_log_level=logging.DEBUG)
            )
            return library_name, check_result

        # Gather all check results concurrently
        check_results: dict[str, ResultPayload] = {}
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(check_library_for_update(lib)) for lib in libraries_to_check]

        # Collect results from completed tasks
        for task in tasks:
            library_name, result = task.result()
            check_results[library_name] = result

        # Process check results and determine which libraries need updates
        libraries_checked = len(libraries_to_check)
        libraries_updated = 0
        libraries_to_update: list[LibraryUpdateInfo] = []

        for library_name, check_result in check_results.items():
            if not isinstance(check_result, CheckLibraryUpdateResultSuccess):
                logger.warning(
                    "Failed to check for updates for library '%s', skipping: %s",
                    library_name,
                    str(check_result.result_details),
                )
                continue

            if not check_result.has_update:
                logger.info("Library '%s' is up to date (version %s)", library_name, check_result.current_version)
                continue

            # Library has an update available
            old_version = check_result.current_version or "unknown"
            new_version = check_result.latest_version or "unknown"
            logger.info("Library '%s' has update available: %s -> %s", library_name, old_version, new_version)
            libraries_to_update.append(
                LibraryUpdateInfo(library_name=library_name, old_version=old_version, new_version=new_version)
            )

        # Update libraries concurrently using task group
        async def update_library(library_name: str, old_version: str, new_version: str) -> LibraryUpdateResult:
            """Update a single library."""
            logger.info("Updating library '%s' from %s to %s", library_name, old_version, new_version)
            update_result = await GriptapeNodes.ahandle_request(
                UpdateLibraryRequest(
                    library_name=library_name,
                    overwrite_existing=request.overwrite_existing,
                )
            )
            return LibraryUpdateResult(
                library_name=library_name,
                old_version=old_version,
                new_version=new_version,
                result=update_result,
            )

        # Gather all update results concurrently
        async with asyncio.TaskGroup() as tg:
            update_tasks = [
                tg.create_task(update_library(info.library_name, info.old_version, info.new_version))
                for info in libraries_to_update
            ]

        # Collect update results
        for task in update_tasks:
            result = task.result()
            library_name = result.library_name
            old_version = result.old_version
            new_version = result.new_version
            update_result = result.result

            if not isinstance(update_result, UpdateLibraryResultSuccess):
                logger.error("Failed to update library '%s': %s", library_name, update_result.result_details)
                update_summary[library_name] = {
                    "old_version": old_version,
                    "new_version": old_version,
                    "status": "failed",
                    "error": update_result.result_details,
                }
                continue

            libraries_updated += 1
            update_summary[library_name] = {
                "old_version": update_result.old_version,
                "new_version": update_result.new_version,
                "status": "updated",
            }
            logger.info(
                "Successfully updated library '%s' from %s to %s",
                library_name,
                update_result.old_version,
                update_result.new_version,
            )

        # Build result details
        details = f"Downloaded {libraries_downloaded} libraries. Checked {libraries_checked} libraries. {libraries_updated} updated."
        logger.info(details)
        return SyncLibrariesResultSuccess(
            libraries_downloaded=libraries_downloaded,
            libraries_checked=libraries_checked,
            libraries_updated=libraries_updated,
            update_summary=update_summary,
            result_details=details,
        )

    async def inspect_library_repo_request(self, request: InspectLibraryRepoRequest) -> ResultPayload:
        """Inspect a library's metadata from a git repository without downloading the full repository."""
        git_url = request.git_url
        ref = request.ref

        # Normalize GitHub shorthand to full URL
        from griptape_nodes.utils.git_utils import normalize_github_url, sparse_checkout_library_json

        normalized_url = normalize_github_url(git_url)
        logger.info("Inspecting library metadata from '%s' (ref: %s)", normalized_url, ref)

        # Perform sparse checkout to get library JSON
        try:
            library_version, commit_sha, library_data_raw = sparse_checkout_library_json(normalized_url, ref)
        except GitCloneError as e:
            details = f"Failed to inspect library from {normalized_url}: {e}"
            logger.error(details)
            return InspectLibraryRepoResultFailure(result_details=details)

        # Validate and create LibrarySchema
        try:
            library_schema = LibrarySchema(**library_data_raw)
        except Exception as e:
            details = f"Invalid library schema from {normalized_url}: {e}"
            logger.error(details)
            return InspectLibraryRepoResultFailure(result_details=details)

        # Return success with full library metadata
        details = f"Successfully inspected library '{library_schema.name}' (version {library_version}) from {normalized_url} at commit {commit_sha[:7]}"
        logger.info(details)
        return InspectLibraryRepoResultSuccess(
            library_schema=library_schema,
            commit_sha=commit_sha,
            git_url=normalized_url,
            ref=ref,
            result_details=details,
        )
