from __future__ import annotations

import importlib.util
import json
import logging
import os
import platform
import subprocess
import sys
import sysconfig
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, cast

import uv
from packaging.requirements import InvalidRequirement, Requirement
from pydantic import ValidationError
from rich.align import Align
from rich.box import HEAVY_EDGE
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
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
    GetEngineVersionRequest,
    GetEngineVersionResultSuccess,
)
from griptape_nodes.retained_mode.events.config_events import (
    GetConfigCategoryRequest,
    GetConfigCategoryResultSuccess,
    SetConfigCategoryRequest,
    SetConfigCategoryResultSuccess,
)
from griptape_nodes.retained_mode.events.library_events import (
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
    LoadLibraryMetadataFromFileRequest,
    LoadLibraryMetadataFromFileResultFailure,
    LoadLibraryMetadataFromFileResultSuccess,
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
    UnloadLibraryFromRegistryRequest,
    UnloadLibraryFromRegistryResultFailure,
    UnloadLibraryFromRegistryResultSuccess,
)
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.library_lifecycle.library_directory import LibraryDirectory
from griptape_nodes.retained_mode.managers.library_lifecycle.library_provenance.local_file import (
    LibraryProvenanceLocalFile,
)
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.utils.version_utils import get_complete_version_string

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
    from griptape_nodes.retained_mode.events.base_events import Payload, RequestPayload, ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")
console = Console()


def _find_griptape_uv_bin() -> str:
    """Find the uv binary, checking dedicated Griptape installation first, then system uv.

    Returns:
        Path to the uv binary to use
    """
    # Check for dedicated Griptape uv installation first
    dedicated_uv_path = xdg_data_home() / "griptape_nodes" / "bin" / "uv"
    if dedicated_uv_path.exists():
        return str(dedicated_uv_path)

    # Fall back to system uv installation
    return uv.find_uv_bin()


class LibraryManager:
    SANDBOX_LIBRARY_NAME = "Sandbox Library"

    @dataclass
    class LibraryInfo:
        """Information about a library that was attempted to be loaded.

        Includes the status of the library, the file path, and any problems encountered during loading.
        """

        status: LibraryStatus
        library_path: str
        library_name: str | None = None
        library_version: str | None = None
        problems: list[str] = field(default_factory=list)

    _library_file_path_to_info: dict[str, LibraryInfo]

    @dataclass
    class RegisteredEventHandler:
        """Information regarding an event handler from a registered library."""

        handler: Callable[[RequestPayload], ResultPayload]
        library_data: LibrarySchema

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
        self._library_event_handler_mappings: dict[type[Payload], dict[str, LibraryManager.RegisteredEventHandler]] = {}
        # LibraryDirectory owns the FSMs and manages library lifecycle
        self._library_directory = LibraryDirectory()

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
            GetAllInfoForAllLibrariesRequest, self.get_all_info_for_all_libraries_request
        )
        event_manager.assign_manager_to_request_type(
            LoadMetadataForAllLibrariesRequest, self.load_metadata_for_all_libraries_request
        )
        event_manager.assign_manager_to_request_type(
            UnloadLibraryFromRegistryRequest, self.unload_library_from_registry_request
        )
        event_manager.assign_manager_to_request_type(ReloadAllLibrariesRequest, self.reload_all_libraries_request)

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

        # Create a table with three columns and row dividers
        # Using SQUARE box style which includes row dividers
        table = Table(show_header=True, box=HEAVY_EDGE, show_lines=True, expand=True)
        table.add_column("Library Name", style="green")
        table.add_column("Status", style="green")
        table.add_column("Version", style="green")
        table.add_column("File Path", style="cyan")
        table.add_column("Problems", style="yellow")

        # Status emojis mapping
        status_emoji = {
            LibraryStatus.GOOD: "✅",
            LibraryStatus.FLAWED: "🟡",
            LibraryStatus.UNUSABLE: "❌",
            LibraryStatus.MISSING: "❓",
        }

        # Add rows for each library info
        for lib_info in library_infos:
            # File path column
            file_path = lib_info.library_path
            file_path_text = Text(file_path, style="cyan")
            file_path_text.overflow = "fold"  # Force wrapping

            # Library name column with emoji based on status
            emoji = status_emoji.get(lib_info.status, "ERROR: Unknown/Unexpected Library Status")
            name = lib_info.library_name if lib_info.library_name else "*UNKNOWN*"
            library_name = f"{emoji} {name}"

            library_version = lib_info.library_version
            if library_version:
                version_str = str(library_version)
            else:
                version_str = "*UNKNOWN*"

            # Problems column - format with numbers if there's more than one
            if not lib_info.problems:
                problems = "No problems detected."
            elif len(lib_info.problems) == 1:
                problems = lib_info.problems[0]
            else:
                # Number the problems when there's more than one
                problems = "\n".join([f"{j + 1}. {problem}" for j, problem in enumerate(lib_info.problems)])

            # Add the row to the table
            table.add_row(library_name, lib_info.status.value, version_str, file_path_text, problems)

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
    ) -> None:
        """Register an event handler for a specific request type from a library."""
        if self._library_event_handler_mappings.get(request_type) is None:
            self._library_event_handler_mappings[request_type] = {}
        self._library_event_handler_mappings[request_type][library_data.name] = LibraryManager.RegisteredEventHandler(
            handler=handler, library_data=library_data
        )

    def get_registered_event_handlers(self, request_type: type[Payload]) -> dict[str, RegisteredEventHandler]:
        """Get all registered event handlers for a specific request type."""
        return self._library_event_handler_mappings.get(request_type, {})

    def on_list_capable_event_handlers(self, request: ListCapableLibraryEventHandlersRequest) -> ResultPayload:
        """Get all registered event handlers for a specific request type."""
        request_type = PayloadRegistry.get_type(request.request_type)
        if request_type is None:
            return ListCapableLibraryEventHandlersResultFailure(
                exception=KeyError(f"Request type '{request.request_type}' is not registered in the PayloadRegistry.")
            )
        handler_mappings = self.get_registered_event_handlers(request_type)
        return ListCapableLibraryEventHandlersResultSuccess(handlers=list(handler_mappings.keys()))

    def on_list_registered_libraries_request(self, _request: ListRegisteredLibrariesRequest) -> ResultPayload:
        # Make a COPY of the list
        snapshot_list = LibraryRegistry.list_libraries()
        event_copy = snapshot_list.copy()

        details = "Successfully retrieved the list of registered libraries."
        logger.debug(details)

        result = ListRegisteredLibrariesResultSuccess(
            libraries=event_copy,
        )
        return result

    def on_list_node_types_in_library_request(self, request: ListNodeTypesInLibraryRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to list node types in a Library named '{request.library}'. Failed because no Library with that name was registered."
            logger.error(details)

            result = ListNodeTypesInLibraryResultFailure()
            return result

        # Cool, get a copy of the list.
        snapshot_list = library.get_registered_nodes()
        event_copy = snapshot_list.copy()

        details = f"Successfully retrieved the list of node types in the Library named '{request.library}'."
        logger.debug(details)

        result = ListNodeTypesInLibraryResultSuccess(
            node_types=event_copy,
        )
        return result

    def get_library_metadata_request(self, request: GetLibraryMetadataRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get metadata for Library '{request.library}'. Failed because no Library with that name was registered."
            logger.error(details)

            result = GetLibraryMetadataResultFailure()
            return result

        # Get the metadata off of it.
        metadata = library.get_metadata()
        details = f"Successfully retrieved metadata for Library '{request.library}'."
        logger.debug(details)

        result = GetLibraryMetadataResultSuccess(metadata=metadata)
        return result

    def load_library_metadata_from_file_request(self, request: LoadLibraryMetadataFromFileRequest) -> ResultPayload:
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
            logger.error(details)
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=None,
                status=LibraryStatus.MISSING,
                problems=[
                    "Library could not be found at the file path specified. It will be removed from the configuration."
                ],
            )

        # Load the JSON
        try:
            with json_path.open("r", encoding="utf-8") as f:
                library_json = json.load(f)
        except json.JSONDecodeError:
            details = f"Attempted to load Library JSON file. Failed because the file at path '{json_path}' was improperly formatted."
            logger.error(details)
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=None,
                status=LibraryStatus.UNUSABLE,
                problems=["Library file not formatted as proper JSON."],
            )
        except Exception as err:
            details = f"Attempted to load Library JSON file from location '{json_path}'. Failed because an exception occurred: {err}"
            logger.error(details)
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=None,
                status=LibraryStatus.UNUSABLE,
                problems=[f"Exception occurred when attempting to load the library: {err}."],
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
                problem = f"Error in section '{loc}': {error_type}, {msg}"
                problems.append(problem)
            details = f"Attempted to load Library JSON file. Failed because the file at path '{json_path}' failed to match the library schema due to: {err}"
            logger.error(details)
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=library_name,
                status=LibraryStatus.UNUSABLE,
                problems=problems,
            )
        except Exception as err:
            details = f"Attempted to load Library JSON file. Failed because the file at path '{json_path}' failed to match the library schema due to: {err}"
            logger.error(details)
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=file_path,
                library_name=library_name,
                status=LibraryStatus.UNUSABLE,
                problems=[f"Library file did not match the library schema specified due to: {err}"],
            )

        details = f"Successfully loaded library metadata from JSON file at {json_path}"
        logger.debug(details)
        return LoadLibraryMetadataFromFileResultSuccess(library_schema=library_data, file_path=file_path)

    def load_metadata_for_all_libraries_request(self, request: LoadMetadataForAllLibrariesRequest) -> ResultPayload:  # noqa: ARG002
        """Load metadata for all libraries from configuration without loading node modules.

        This loads metadata from both library JSON files specified in configuration
        and generates sandbox library metadata by scanning Python files without importing them.
        """
        successful_libraries = []
        failed_libraries = []

        # Load metadata from config libraries
        config_mgr = GriptapeNodes.ConfigManager()
        user_libraries_section = "app_events.on_app_initialization_complete.libraries_to_register"
        libraries_to_register: list[str] = config_mgr.get_config_value(user_libraries_section)

        if libraries_to_register is not None:
            for library_to_register in libraries_to_register:
                if library_to_register and library_to_register.endswith(".json"):
                    # Load metadata for this library file
                    metadata_request = LoadLibraryMetadataFromFileRequest(file_path=library_to_register)
                    metadata_result = self.load_library_metadata_from_file_request(metadata_request)

                    if isinstance(metadata_result, LoadLibraryMetadataFromFileResultSuccess):
                        successful_libraries.append(metadata_result)
                    else:
                        failed_libraries.append(cast("LoadLibraryMetadataFromFileResultFailure", metadata_result))
                # Note: We skip requirement specifier libraries (non-.json) as they don't have
                # JSON files we can load metadata from without installation

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
        logger.debug(details)
        return LoadMetadataForAllLibrariesResultSuccess(
            successful_libraries=successful_libraries,
            failed_libraries=failed_libraries,
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
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=sandbox_library_dir_as_posix,
                library_name=LibraryManager.SANDBOX_LIBRARY_NAME,
                status=LibraryStatus.MISSING,
                problems=["Sandbox directory does not exist."],
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
            return LoadLibraryMetadataFromFileResultFailure(
                library_path=sandbox_library_dir_as_posix,
                library_name=LibraryManager.SANDBOX_LIBRARY_NAME,
                status=LibraryStatus.UNUSABLE,
                problems=["Could not get engine version for sandbox library generation."],
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

        details = f"Successfully generated sandbox library metadata with {len(node_definitions)} nodes from {sandbox_library_dir}"
        logger.debug(details)
        return LoadLibraryMetadataFromFileResultSuccess(
            library_schema=library_schema, file_path=str(sandbox_library_dir)
        )

    def get_node_metadata_from_library_request(self, request: GetNodeMetadataFromLibraryRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get node metadata for a node type '{request.node_type}' in a Library named '{request.library}'. Failed because no Library with that name was registered."
            logger.error(details)

            result = GetNodeMetadataFromLibraryResultFailure()
            return result

        # Does the node type exist within the library?
        try:
            metadata = library.get_node_metadata(node_type=request.node_type)
        except KeyError:
            details = f"Attempted to get node metadata for a node type '{request.node_type}' in a Library named '{request.library}'. Failed because no node type of that name could be found in the Library."
            logger.error(details)

            result = GetNodeMetadataFromLibraryResultFailure()
            return result

        details = f"Successfully retrieved node metadata for a node type '{request.node_type}' in a Library named '{request.library}'."
        logger.debug(details)

        result = GetNodeMetadataFromLibraryResultSuccess(
            metadata=metadata,
        )
        return result

    def list_categories_in_library_request(self, request: ListCategoriesInLibraryRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get categories in a Library named '{request.library}'. Failed because no Library with that name was registered."
            logger.error(details)
            result = ListCategoriesInLibraryResultFailure()
            return result

        categories = library.get_categories()
        result = ListCategoriesInLibraryResultSuccess(categories=categories)
        return result

    def register_library_from_file_request(self, request: RegisterLibraryFromFileRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915 (complex logic needs branches)
        file_path = request.file_path

        # Convert to Path object if it's a string
        json_path = Path(file_path)

        # Check if the file exists
        if not json_path.exists():
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=None,
                status=LibraryStatus.MISSING,
                problems=[
                    "Library could not be found at the file path specified. It will be removed from the configuration."
                ],
            )
            details = f"Attempted to load Library JSON file. Failed because no file could be found at the specified path: {json_path}"
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Use the new metadata loading functionality
        metadata_request = LoadLibraryMetadataFromFileRequest(file_path=file_path)
        metadata_result = self.load_library_metadata_from_file_request(metadata_request)

        if not isinstance(metadata_result, LoadLibraryMetadataFromFileResultSuccess):
            # Metadata loading failed, use the detailed error information from the failure result
            failure_result = cast("LoadLibraryMetadataFromFileResultFailure", metadata_result)

            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=failure_result.library_name,
                status=failure_result.status,
                problems=failure_result.problems,
            )
            return RegisterLibraryFromFileResultFailure()

        # Get the validated library data
        library_data = metadata_result.library_schema

        # Make sure the version string is copacetic.
        library_version = library_data.metadata.library_version
        if library_version is None:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_data.name,
                status=LibraryStatus.UNUSABLE,
                problems=[
                    f"Library's version string '{library_data.metadata.library_version}' wasn't valid. Must be in major.minor.patch format."
                ],
            )
            details = f"Attempted to load Library '{library_data.name}' JSON file from '{json_path}'. Failed because version string '{library_data.metadata.library_version}' wasn't valid. Must be in major.minor.patch format."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Get the directory containing the JSON file to resolve relative paths
        base_dir = json_path.parent.absolute()
        # Add the directory to the Python path to allow for relative imports
        sys.path.insert(0, str(base_dir))

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
                    library_path=file_path,
                    library_name=library_data.name,
                    library_version=library_version,
                    status=LibraryStatus.UNUSABLE,
                    problems=[
                        f"Failed to load Advanced Library module from '{library_data.advanced_library_path}': {err}"
                    ],
                )
                details = f"Attempted to load Library '{library_data.name}' from '{json_path}'. Failed to load Advanced Library module: {err}"
                logger.error(details)
                return RegisterLibraryFromFileResultFailure()

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
                library_path=file_path,
                library_name=library_data.name,
                library_version=library_version,
                status=LibraryStatus.UNUSABLE,
                problems=[
                    "Failed because a library with this name was already registered. Check the Settings to ensure duplicate libraries are not being loaded."
                ],
            )

            details = f"Attempted to load Library JSON file from '{json_path}'. Failed because a Library '{library_data.name}' already exists. Error: {err}."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Install node library dependencies
        try:
            if library_data.metadata.dependencies and library_data.metadata.dependencies.pip_dependencies:
                pip_install_flags = library_data.metadata.dependencies.pip_install_flags
                if pip_install_flags is None:
                    pip_install_flags = []
                pip_dependencies = library_data.metadata.dependencies.pip_dependencies

                # Determine venv path for dependency installation
                venv_path = self._get_library_venv_path(library_data.name, file_path)

                # Only install dependencies if conditions are met
                try:
                    library_venv_python_path = self._init_library_venv(venv_path)
                except RuntimeError as e:
                    self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                        library_path=file_path,
                        library_name=library_data.name,
                        library_version=library_version,
                        status=LibraryStatus.UNUSABLE,
                        problems=[str(e)],
                    )
                    details = f"Attempted to load Library JSON file from '{json_path}'. Failed when creating the virtual environment: {e}."
                    logger.error(details)
                    return RegisterLibraryFromFileResultFailure()
                if self._can_write_to_venv_location(library_venv_python_path):
                    # Check disk space before installing dependencies
                    config_manager = GriptapeNodes.ConfigManager()
                    min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_libraries")
                    if not OSManager.check_available_disk_space(Path(venv_path), min_space_gb):
                        error_msg = OSManager.format_disk_space_error(Path(venv_path))
                        logger.error(
                            "Attempted to load Library JSON from '%s'. Failed when installing dependencies (requires %.1f GB): %s",
                            json_path,
                            min_space_gb,
                            error_msg,
                        )
                        self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                            library_path=file_path,
                            library_name=library_data.name,
                            library_version=library_version,
                            status=LibraryStatus.UNUSABLE,
                            problems=[
                                f"Insufficient disk space for dependencies (requires {min_space_gb} GB): {error_msg}"
                            ],
                        )
                        return RegisterLibraryFromFileResultFailure()

                    # Grab the python executable from the virtual environment so that we can pip install there
                    logger.info(
                        "Installing dependencies for library '%s' with pip in venv at %s", library_data.name, venv_path
                    )
                    subprocess.run(  # noqa: S603
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
                        capture_output=True,
                        text=True,
                    )
                else:
                    logger.debug(
                        "Skipping dependency installation for library '%s' - venv location at %s is not writable",
                        library_data.name,
                        venv_path,
                    )
        except subprocess.CalledProcessError as e:
            # Failed to create the library
            error_details = f"return code={e.returncode}, stdout={e.stdout}, stderr={e.stderr}"

            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_data.name,
                library_version=library_version,
                status=LibraryStatus.UNUSABLE,
                problems=[f"Dependency installation failed: {error_details}"],
            )
            details = f"Attempted to load Library JSON file from '{json_path}'. Failed when installing dependencies: {error_details}"
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # We are at least potentially viable.
        # Record all problems that occurred
        problems = []

        # Check the library's custom config settings.
        if library_data.settings is not None:
            # Assign them into the config space.
            for library_data_setting in library_data.settings:
                # Does the category exist?
                get_category_request = GetConfigCategoryRequest(category=library_data_setting.category)
                get_category_result = GriptapeNodes.handle_request(get_category_request)
                if not isinstance(get_category_result, GetConfigCategoryResultSuccess):
                    # That's OK, we'll invent it. Or at least we'll try.
                    create_new_category_request = SetConfigCategoryRequest(
                        category=library_data_setting.category, contents=library_data_setting.contents
                    )
                    create_new_category_result = GriptapeNodes.handle_request(create_new_category_request)
                    if not isinstance(create_new_category_result, SetConfigCategoryResultSuccess):
                        problems.append(f"Failed to create new config category '{library_data_setting.category}'.")
                        details = f"Failed attempting to create new config category '{library_data_setting.category}' for library '{library_data.name}'."
                        logger.error(details)
                        continue  # SKIP IT
                else:
                    # We had an existing category. Union our changes into it (not replacing anything that matched).
                    existing_category_contents = get_category_result.contents
                    existing_category_contents |= {
                        k: v for k, v in library_data_setting.contents.items() if k not in existing_category_contents
                    }
                    set_category_request = SetConfigCategoryRequest(
                        category=library_data_setting.category, contents=existing_category_contents
                    )
                    set_category_result = GriptapeNodes.handle_request(set_category_request)
                    if not isinstance(set_category_result, SetConfigCategoryResultSuccess):
                        problems.append(f"Failed to update config category '{library_data_setting.category}'.")
                        details = f"Failed attempting to update config category '{library_data_setting.category}' for library '{library_data.name}'."
                        logger.error(details)
                        continue  # SKIP IT

        # Attempt to load nodes from the library.
        library_load_results = self._attempt_load_nodes_from_library(
            library_data=library_data,
            library=library,
            base_dir=base_dir,
            library_file_path=file_path,
            library_version=library_version,
            problems=problems,
        )
        self._library_file_path_to_info[file_path] = library_load_results

        match library_load_results.status:
            case LibraryStatus.GOOD:
                details = f"Successfully loaded Library '{library_data.name}' from JSON file at {json_path}"
                logger.info(details)
                return RegisterLibraryFromFileResultSuccess(library_name=library_data.name)
            case LibraryStatus.FLAWED:
                details = f"Successfully loaded Library JSON file from '{json_path}', but one or more nodes failed to load. Check the log for more details."
                logger.warning(details)
                return RegisterLibraryFromFileResultSuccess(library_name=library_data.name)
            case LibraryStatus.UNUSABLE:
                details = f"Attempted to load Library JSON file from '{json_path}'. Failed because no nodes were loaded. Check the log for more details."
                logger.error(details)
                return RegisterLibraryFromFileResultFailure()
            case _:
                details = f"Attempted to load Library JSON file from '{json_path}'. Failed because an unknown/unexpected status '{library_load_results.status}' was returned."
                logger.error(details)
                return RegisterLibraryFromFileResultFailure()

    def register_library_from_requirement_specifier_request(
        self, request: RegisterLibraryFromRequirementSpecifierRequest
    ) -> ResultPayload:
        try:
            package_name = Requirement(request.requirement_specifier).name
            # Determine venv path for dependency installation
            venv_path = self._get_library_venv_path(package_name, None)

            # Only install dependencies if conditions are met
            try:
                library_python_venv_path = self._init_library_venv(venv_path)
            except RuntimeError as e:
                details = f"Attempted to install library '{request.requirement_specifier}'. Failed when creating the virtual environment: {e}"
                logger.error(details)
                return RegisterLibraryFromRequirementSpecifierResultFailure()
            if self._can_write_to_venv_location(library_python_venv_path):
                # Check disk space before installing dependencies
                config_manager = GriptapeNodes.ConfigManager()
                min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_libraries")
                if not OSManager.check_available_disk_space(Path(venv_path), min_space_gb):
                    error_msg = OSManager.format_disk_space_error(Path(venv_path))
                    logger.error(
                        "Attempted to install library '%s'. Failed when installing dependencies (requires %.1f GB): %s",
                        request.requirement_specifier,
                        min_space_gb,
                        error_msg,
                    )
                    return RegisterLibraryFromRequirementSpecifierResultFailure()

                logger.info("Installing dependency '%s' with pip in venv at %s", package_name, venv_path)
                subprocess.run(  # noqa: S603
                    [
                        _find_griptape_uv_bin(),
                        "pip",
                        "install",
                        request.requirement_specifier,
                        "--python",
                        library_python_venv_path,
                    ],
                    check=True,
                    capture_output=True,
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
            logger.error(details)
            return RegisterLibraryFromRequirementSpecifierResultFailure()
        except InvalidRequirement as e:
            details = f"Attempted to install library '{request.requirement_specifier}'. Failed due to invalid requirement specifier: {e}"
            logger.error(details)
            return RegisterLibraryFromRequirementSpecifierResultFailure()

        library_path = str(files(package_name).joinpath(request.library_config_name))

        register_result = GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path=library_path))
        if isinstance(register_result, RegisterLibraryFromFileResultFailure):
            details = f"Attempted to install library '{request.requirement_specifier}'. Failed due to {register_result}"
            logger.error(details)
            return RegisterLibraryFromRequirementSpecifierResultFailure()

        return RegisterLibraryFromRequirementSpecifierResultSuccess(library_name=request.requirement_specifier)

    def _init_library_venv(self, library_venv_path: Path) -> Path:
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
                logger.info("Creating virtual environment at %s with Python %s", library_venv_path, python_version)
                subprocess.run(  # noqa: S603
                    [sys.executable, "-m", "uv", "venv", str(library_venv_path), "--python", python_version],
                    check=True,
                    capture_output=True,
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

        # Need to insert into the path so that the library picks up on the venv
        site_packages = str(
            Path(
                sysconfig.get_path(
                    "purelib",
                    vars={"base": str(library_venv_path), "platbase": str(library_venv_path)},
                )
            )
        )
        sys.path.insert(0, site_packages)

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
            logger.error(details)
            return UnloadLibraryFromRegistryResultFailure()

        # Clean up all stable module aliases for this library
        self._unregister_all_stable_module_aliases_for_library(request.library_name)

        # Remove the library from our library info list. This prevents it from still showing
        # up in the table of attempted library loads.
        lib_info = self.get_library_info_by_library_name(request.library_name)
        if lib_info:
            del self._library_file_path_to_info[lib_info.library_path]

        details = f"Successfully unloaded (and unregistered) library '{request.library_name}'."
        logger.debug(details)
        return UnloadLibraryFromRegistryResultSuccess()

    def get_all_info_for_all_libraries_request(self, request: GetAllInfoForAllLibrariesRequest) -> ResultPayload:  # noqa: ARG002
        list_libraries_request = ListRegisteredLibrariesRequest()
        list_libraries_result = self.on_list_registered_libraries_request(list_libraries_request)

        if not list_libraries_result.succeeded():
            details = "Attempted to get all info for all libraries, but listing the registered libraries failed."
            logger.error(details)
            return GetAllInfoForAllLibrariesResultFailure()

        try:
            list_libraries_success = cast("ListRegisteredLibrariesResultSuccess", list_libraries_result)

            # Create a mapping of library name to all its info.
            library_name_to_all_info = {}

            for library_name in list_libraries_success.libraries:
                library_all_info_request = GetAllInfoForLibraryRequest(library=library_name)
                library_all_info_result = self.get_all_info_for_library_request(library_all_info_request)

                if not library_all_info_result.succeeded():
                    details = f"Attempted to get all info for all libraries, but failed when getting all info for library named '{library_name}'."
                    logger.error(details)
                    return GetAllInfoForAllLibrariesResultFailure()

                library_all_info_success = cast("GetAllInfoForLibraryResultSuccess", library_all_info_result)

                library_name_to_all_info[library_name] = library_all_info_success
        except Exception as err:
            details = f"Attempted to get all info for all libraries. Encountered error {err}."
            logger.error(details)
            return GetAllInfoForAllLibrariesResultFailure()

        # We're home free now
        details = "Successfully retrieved all info for all libraries."
        logger.debug(details)
        result = GetAllInfoForAllLibrariesResultSuccess(library_name_to_library_info=library_name_to_all_info)
        return result

    def get_all_info_for_library_request(self, request: GetAllInfoForLibraryRequest) -> ResultPayload:  # noqa: PLR0911
        # Does this library exist?
        try:
            LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed because no Library with that name was registered."
            logger.error(details)
            result = GetAllInfoForLibraryResultFailure()
            return result

        library_metadata_request = GetLibraryMetadataRequest(library=request.library)
        library_metadata_result = self.get_library_metadata_request(library_metadata_request)

        if not library_metadata_result.succeeded():
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the library's metadata."
            logger.error(details)
            return GetAllInfoForLibraryResultFailure()

        list_categories_request = ListCategoriesInLibraryRequest(library=request.library)
        list_categories_result = self.list_categories_in_library_request(list_categories_request)

        if not list_categories_result.succeeded():
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the list of categories in the library."
            logger.error(details)
            return GetAllInfoForLibraryResultFailure()

        node_type_list_request = ListNodeTypesInLibraryRequest(library=request.library)
        node_type_list_result = self.on_list_node_types_in_library_request(node_type_list_request)

        if not node_type_list_result.succeeded():
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the list of node types in the library."
            logger.error(details)
            return GetAllInfoForLibraryResultFailure()

        # Cast everyone to their success counterparts.
        try:
            library_metadata_result_success = cast("GetLibraryMetadataResultSuccess", library_metadata_result)
            list_categories_result_success = cast("ListCategoriesInLibraryResultSuccess", list_categories_result)
            node_type_list_result_success = cast("ListNodeTypesInLibraryResultSuccess", node_type_list_result)
        except Exception as err:
            details = (
                f"Attempted to get all library info for a Library named '{request.library}'. Encountered error: {err}."
            )
            logger.error(details)
            return GetAllInfoForLibraryResultFailure()

        # Now build the map of node types to metadata.
        node_type_name_to_node_metadata_details = {}
        for node_type_name in node_type_list_result_success.node_types:
            node_metadata_request = GetNodeMetadataFromLibraryRequest(library=request.library, node_type=node_type_name)
            node_metadata_result = self.get_node_metadata_from_library_request(node_metadata_request)

            if not node_metadata_result.succeeded():
                details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the metadata for a node type called '{node_type_name}'."
                logger.error(details)
                return GetAllInfoForLibraryResultFailure()

            try:
                node_metadata_result_success = cast("GetNodeMetadataFromLibraryResultSuccess", node_metadata_result)
            except Exception as err:
                details = f"Attempted to get all library info for a Library named '{request.library}'. Encountered error: {err}."
                logger.error(details)
                return GetAllInfoForLibraryResultFailure()

            # Put it into the map.
            node_type_name_to_node_metadata_details[node_type_name] = node_metadata_result_success

        details = f"Successfully got all library info for a Library named '{request.library}'."
        logger.debug(details)
        result = GetAllInfoForLibraryResultSuccess(
            library_metadata_details=library_metadata_result_success,
            category_details=list_categories_result_success,
            node_type_name_to_node_metadata_details=node_type_name_to_node_metadata_details,
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

    def load_all_libraries_from_config(self) -> None:
        # Comment out lines 1503-1545 and call the _load libraries from provenance system to test the other functionality.

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
                library_path=failed_library.library_path,
                library_name=failed_library.library_name,
                status=failed_library.status,
                problems=failed_library.problems,
            )

        # Use metadata results to selectively load libraries
        user_libraries_section = "app_events.on_app_initialization_complete.libraries_to_register"

        # Load libraries that had successful metadata loading
        for library_result in metadata_result.successful_libraries:
            if library_result.library_schema.name == LibraryManager.SANDBOX_LIBRARY_NAME:
                # Handle sandbox library - use the schema we already have
                self._attempt_generate_sandbox_library_from_schema(
                    library_schema=library_result.library_schema, sandbox_directory=library_result.file_path
                )
            else:
                # Handle config-based library - register it directly using the file path
                register_request = RegisterLibraryFromFileRequest(
                    file_path=library_result.file_path, load_as_default_library=False
                )
                register_result = self.register_library_from_file_request(register_request)
                if isinstance(register_result, RegisterLibraryFromFileResultFailure):
                    # Registration failed - the failure info is already recorded in _library_file_path_to_info
                    # by register_library_from_file_request, so we just log it here for visibility
                    logger.warning(f"Failed to register library from {library_result.file_path}")  # noqa: G004

        # Print 'em all pretty
        self.print_library_load_status()

        # Remove any missing libraries AFTER we've printed them for the user.
        user_libraries_section = "app_events.on_app_initialization_complete.libraries_to_register"
        self._remove_missing_libraries_from_config(config_category=user_libraries_section)

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        GriptapeNodes.EngineIdentityManager().initialize_engine_id()
        GriptapeNodes.SessionManager().get_saved_session_id()

        # App just got init'd. See if there are library JSONs to load!
        self.load_all_libraries_from_config()

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

        nodes_app_url = os.getenv("GRIPTAPE_NODES_UI_BASE_URL", "https://nodes.griptape.ai")
        message = Panel(
            Align.center(
                f"[bold green]Engine is ready to receive events[/bold green]\n"
                f"[bold blue]Return to: [link={nodes_app_url}]{nodes_app_url}[/link] to access the Workflow Editor[/bold blue]",
                vertical="middle",
            ),
            title="🚀 Griptape Nodes Engine Started",
            subtitle=f"[green]{engine_version}{session_info}[/green]",
            border_style="green",
            padding=(1, 4),
        )
        console.print(message)

    def _load_libraries_from_provenance_system(self) -> None:
        """Load libraries using the new provenance-based system with FSM.

        This method converts libraries_to_register entries into LibraryProvenanceLocalFile
        objects and processes them through the LibraryDirectory and LibraryLifecycleFSM systems.
        """
        # Get config manager
        config_mgr = GriptapeNodes.ConfigManager()

        # Get the current libraries_to_register list
        user_libraries_section = "app_events.on_app_initialization_complete.libraries_to_register"
        libraries_to_register: list[str] = config_mgr.get_config_value(user_libraries_section)

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
            self._library_directory.add_user_candidate(provenance)

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
            if self._library_directory.install_library(candidate.provenance):
                self._library_directory.load_library(candidate.provenance)

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
        problems: list[str],
    ) -> LibraryManager.LibraryInfo:
        any_nodes_loaded_successfully = False

        # Check for version-based compatibility issues and add to problems
        version_issues = GriptapeNodes.VersionCompatibilityManager().check_library_version_compatibility(library_data)
        has_disqualifying_issues = False
        for issue in version_issues:
            problems.append(issue.message)
            if issue.severity == LibraryStatus.UNUSABLE:
                has_disqualifying_issues = True

        # Early exit if any version issues are disqualifying
        if has_disqualifying_issues:
            return LibraryManager.LibraryInfo(
                library_path=library_file_path,
                library_name=library_data.name,
                library_version=library_version,
                status=LibraryStatus.UNUSABLE,
                problems=problems,
            )

        # Call the before_library_nodes_loaded callback if available
        advanced_library = library.get_advanced_library()
        if advanced_library:
            try:
                advanced_library.before_library_nodes_loaded(library_data, library)
                details = f"Successfully called before_library_nodes_loaded callback for library '{library_data.name}'"
                logger.debug(details)
            except Exception as err:
                problem = f"Error calling before_library_nodes_loaded callback: {err}"
                problems.append(problem)
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
            except Exception as err:
                problems.append(
                    f"Failed to load node '{node_definition.class_name}' from '{node_file_path}' with error: {err}"
                )
                details = f"Attempted to load node '{node_definition.class_name}' from '{node_file_path}'. Failed because an exception occurred: {err}"
                logger.error(details)
                continue  # SKIP IT

            try:
                # Register the node type with the library
                forensics_string = library.register_new_node_type(node_class, metadata=node_definition.metadata)
                if forensics_string is not None:
                    problems.append(forensics_string)
            except Exception as err:
                problems.append(
                    f"Failed to register node '{node_definition.class_name}' from '{node_file_path}' with error: {err}"
                )
                details = f"Attempted to load node '{node_definition.class_name}' from '{node_file_path}'. Failed because an exception occurred: {err}"
                logger.error(details)
                continue  # SKIP IT

            # If we got here, at least one node came in.
            any_nodes_loaded_successfully = True

        # Call the after_library_nodes_loaded callback if available
        if advanced_library:
            try:
                advanced_library.after_library_nodes_loaded(library_data, library)
                details = f"Successfully called after_library_nodes_loaded callback for library '{library_data.name}'"
                logger.debug(details)
            except Exception as err:
                problem = f"Error calling after_library_nodes_loaded callback: {err}"
                problems.append(problem)
                details = f"Failed to call after_library_nodes_loaded callback for library '{library_data.name}': {err}"
                logger.error(details)

        # Create a LibraryInfo object based on load successes and problem count.
        if not any_nodes_loaded_successfully:
            status = LibraryStatus.UNUSABLE
        elif problems:
            # Success, but errors.
            status = LibraryStatus.FLAWED
        else:
            # Flawless victory.
            status = LibraryStatus.GOOD

        # Create a LibraryInfo object based on load successes and problem count.
        return LibraryManager.LibraryInfo(
            library_path=library_file_path,
            library_name=library_data.name,
            library_version=library_version,
            status=status,
            problems=problems,
        )

    def _attempt_generate_sandbox_library_from_schema(
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
                problems.append(f"Could not load module in sandbox library '{candidate_path}': {err}")
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
                library_path=sandbox_library_dir_as_posix,
                library_name=library_data.name,
                library_version=library_data.metadata.library_version,
                status=LibraryStatus.UNUSABLE,
                problems=[
                    "Failed because a library with this name was already registered. Check the Settings to ensure duplicate libraries are not being loaded."
                ],
            )

            details = f"Attempted to load Library JSON file from '{sandbox_library_dir}'. Failed because a Library '{library_data.name}' already exists. Error: {err}."
            logger.error(details)
            return

        # Load nodes into the library
        library_load_results = self._attempt_load_nodes_from_library(
            library_data=library_data,
            library=library,
            base_dir=sandbox_library_dir,
            library_file_path=sandbox_library_dir_as_posix,
            library_version=library_data.metadata.library_version,
            problems=problems,
        )
        self._library_file_path_to_info[sandbox_library_dir_as_posix] = library_load_results

    def _find_files_in_dir(self, directory: Path, extension: str) -> list[Path]:
        ret_val = []
        for root, _, files_found in os.walk(directory):
            for file in files_found:
                if file.endswith(extension):
                    file_path = Path(root) / file
                    ret_val.append(file_path)
        return ret_val

    def _load_libraries_from_config_category(self, config_category: str, *, load_as_default_library: bool) -> None:
        config_mgr = GriptapeNodes.ConfigManager()
        libraries_to_register_category: list[str] = config_mgr.get_config_value(config_category)

        if libraries_to_register_category is not None:
            for library_to_register in libraries_to_register_category:
                if library_to_register:
                    if library_to_register.endswith(".json"):
                        library_load_request = RegisterLibraryFromFileRequest(
                            file_path=library_to_register,
                            load_as_default_library=load_as_default_library,
                        )
                    else:
                        library_load_request = RegisterLibraryFromRequirementSpecifierRequest(
                            requirement_specifier=library_to_register
                        )
                    GriptapeNodes.handle_request(library_load_request)

    def _remove_missing_libraries_from_config(self, config_category: str) -> None:
        # Now remove all libraries that were missing from the user's config.
        config_mgr = GriptapeNodes.ConfigManager()
        libraries_to_register_category = config_mgr.get_config_value(config_category)

        paths_to_remove = set()
        for library_path, library_info in self._library_file_path_to_info.items():
            if library_info.status == LibraryStatus.MISSING:
                # Remove this file path from the config.
                paths_to_remove.add(library_path.lower())

        if paths_to_remove and libraries_to_register_category:
            libraries_to_register_category = [
                library for library in libraries_to_register_category if library.lower() not in paths_to_remove
            ]
            config_mgr.set_config_value(config_category, libraries_to_register_category)

    def reload_all_libraries_request(self, request: ReloadAllLibrariesRequest) -> ResultPayload:  # noqa: ARG002
        # Start with a clean slate.
        clear_all_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
        clear_all_result = GriptapeNodes.handle_request(clear_all_request)
        if not clear_all_result.succeeded():
            details = "Failed to clear the existing object state when preparing to reload all libraries."
            logger.error(details)
            return ReloadAllLibrariesResultFailure()

        # Unload all libraries now.
        all_libraries_request = ListRegisteredLibrariesRequest()
        all_libraries_result = GriptapeNodes.handle_request(all_libraries_request)
        if not isinstance(all_libraries_result, ListRegisteredLibrariesResultSuccess):
            details = "When preparing to reload all libraries, failed to get registered libraries."
            logger.error(details)
            return ReloadAllLibrariesResultFailure()

        for library_name in all_libraries_result.libraries:
            unload_library_request = UnloadLibraryFromRegistryRequest(library_name=library_name)
            unload_library_result = GriptapeNodes.handle_request(unload_library_request)
            if not unload_library_result.succeeded():
                details = f"When preparing to reload all libraries, failed to unload library '{library_name}'."
                logger.error(details)
                return ReloadAllLibrariesResultFailure()

        # Load (or reload, which should trigger a hot reload) all libraries
        self.load_all_libraries_from_config()

        details = (
            "Successfully reloaded all libraries. All object state was cleared and previous libraries were unloaded."
        )
        logger.info(details)
        return ReloadAllLibrariesResultSuccess()
