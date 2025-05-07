from __future__ import annotations

import importlib.util
import json
import logging
import platform
import subprocess
import sys
import sysconfig
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError
from rich.box import HEAVY_EDGE
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from xdg_base_dirs import xdg_data_home

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
from griptape_nodes.retained_mode.events.app_events import (
    AppInitializationComplete,
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
    ListCategoriesInLibraryRequest,
    ListCategoriesInLibraryResultFailure,
    ListCategoriesInLibraryResultSuccess,
    ListNodeTypesInLibraryRequest,
    ListNodeTypesInLibraryResultFailure,
    ListNodeTypesInLibraryResultSuccess,
    ListRegisteredLibrariesRequest,
    ListRegisteredLibrariesResultSuccess,
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromFileResultFailure,
    RegisterLibraryFromFileResultSuccess,
    UnloadLibraryFromRegistryRequest,
    UnloadLibraryFromRegistryResultFailure,
    UnloadLibraryFromRegistryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.os_manager import OSManager

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class LibraryManager:
    class LibraryStatus(StrEnum):
        """Status of the library that was attempted to be loaded."""

        GOOD = "GOOD"  # No errors detected during loading. Registered.
        FLAWED = "FLAWED"  # Some errors detected, but recoverable. Registered.
        UNUSABLE = "UNUSABLE"  # Errors detected and not recoverable. Not registered.
        MISSING = "MISSING"  # File not found. Not registered.

    @dataclass
    class LibraryInfo:
        """Information about a library that was attempted to be loaded.

        Includes the status of the library, the file path, and any problems encountered during loading.
        """

        status: LibraryManager.LibraryStatus
        library_path: str
        library_name: str | None = None
        library_version: str | None = None
        problems: list[str] = field(default_factory=list)

    _library_file_path_to_info: dict[str, LibraryInfo]

    def __init__(self, event_manager: EventManager) -> None:
        self._library_file_path_to_info = {}

        event_manager.assign_manager_to_request_type(
            ListRegisteredLibrariesRequest, self.on_list_registered_libraries_request
        )
        event_manager.assign_manager_to_request_type(
            ListNodeTypesInLibraryRequest, self.on_list_node_types_in_library_request
        )
        event_manager.assign_manager_to_request_type(
            GetNodeMetadataFromLibraryRequest,
            self.get_node_metadata_from_library_request,
        )
        event_manager.assign_manager_to_request_type(
            RegisterLibraryFromFileRequest,
            self.register_library_from_file_request,
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
            UnloadLibraryFromRegistryRequest, self.unload_library_from_registry_request
        )

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
            LibraryManager.LibraryStatus.GOOD: "✅",
            LibraryManager.LibraryStatus.FLAWED: "🟡",
            LibraryManager.LibraryStatus.UNUSABLE: "❌",
            LibraryManager.LibraryStatus.MISSING: "❓",
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
                status=LibraryManager.LibraryStatus.MISSING,
                problems=[
                    "Library could not be found at the file path specified. It will be removed from the configuration."
                ],
            )
            details = f"Attempted to load Library JSON file. Failed because no file could be found at the specified path: {json_path}"
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Load the JSON
        try:
            with json_path.open("r") as f:
                library_json = json.load(f)
        except json.JSONDecodeError:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=None,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=["Library file not formatted as proper JSON."],
            )
            details = f"Attempted to load Library JSON file. Failed because the file at path '{json_path}' was improperly formatted."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()
        except Exception as err:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=None,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[f"Exception occurred when attempting to load the library: {err}."],
            )
            details = f"Attempted to load Library JSON file from location '{json_path}'. Failed because an exception occurred: {err}"
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

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
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=None,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=problems,
            )
            details = f"Attempted to load Library JSON file. Failed because the file at path '{json_path}' failed to match the library schema due to: {err}"
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()
        except Exception as err:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=None,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[f"Library file did not match the library schema specified due to: {err}"],
            )
            details = f"Attempted to load Library JSON file. Failed because the file at path '{json_path}' failed to match the library schema due to: {err}"
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Make sure the version string is copacetic.
        library_version = library_data.metadata.library_version
        if library_version is None:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_data.name,
                status=LibraryManager.LibraryStatus.UNUSABLE,
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

        # Create or get the library
        try:
            # Try to create a new library
            library = LibraryRegistry.generate_new_library(
                library_data=library_data,
                mark_as_default_library=request.load_as_default_library,
            )

        except KeyError as err:
            # Library already exists
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_data.name,
                library_version=library_version,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[
                    "Failed because a library with this name was already registered. Check the Settings to ensure duplicate libraries are not being loaded."
                ],
            )

            details = f"Attempted to load Library JSON file from '{json_path}'. Failed because a Library '{library_data.name}' already exists. Error: {err}."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Install node library dependencies
        try:
            site_packages = None
            if library_data.metadata.dependencies:
                pip_install_flags = library_data.metadata.dependencies.pip_install_flags
                if pip_install_flags is None:
                    pip_install_flags = []
                pip_dependencies = library_data.metadata.dependencies.pip_dependencies
                if pip_dependencies is None:
                    pip_dependencies = []

                # Create a virtual environment for the library
                python_version = platform.python_version()
                library_venv_path = (
                    xdg_data_home()
                    / "griptape_nodes"
                    / "venvs"
                    / python_version
                    / library_data.name.replace(" ", "_").strip()
                )
                if library_venv_path.exists():
                    logger.debug("Virtual environment already exists at %s", library_venv_path)
                else:
                    subprocess.run(  # noqa: S603
                        [sys.executable, "-m", "uv", "venv", library_venv_path, "--python", python_version],
                        check=True,
                        text=True,
                    )
                    logger.debug("Created virtual environment at %s", library_venv_path)

                # Grab the python executable from the virtual environment so that we can pip install there
                if OSManager.is_windows():
                    library_venv_python_path = library_venv_path / "Scripts" / "python.exe"
                else:
                    library_venv_python_path = library_venv_path / "bin" / "python"
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
                    text=True,
                )
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
        except subprocess.CalledProcessError as e:
            # Failed to create the library
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_data.name,
                library_version=library_version,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[f"Failed to create the library: {e}"],
            )
            details = (
                f"Attempted to load Library JSON file from '{json_path}'. Failed when installing dependencies: {e}."
            )
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
                    existing_category_contents.update(library_data_setting.contents)
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
        any_nodes_loaded_successesfully = False
        # Process each node in the metadata
        for node_definition in library_data.nodes:
            # Resolve relative path to absolute path
            node_file_path = Path(node_definition.file_path)
            if not node_file_path.is_absolute():
                node_file_path = base_dir / node_file_path

            try:
                # Dynamically load the module containing the node class
                node_class = self._load_class_from_file(node_file_path, node_definition.class_name)
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
            any_nodes_loaded_successesfully = True

        if not any_nodes_loaded_successesfully:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_data.name,
                library_version=library_version,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=problems,
            )
            details = f"Attempted to load Library JSON file from '{json_path}'. Failed because no nodes were loaded. Check the log for more details."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Successes, but errors.
        if problems:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_data.name,
                library_version=library_version,
                status=LibraryManager.LibraryStatus.FLAWED,
                problems=problems,
            )
            details = f"Successfully loaded Library JSON file from '{json_path}', but one or more nodes failed to load. Check the log for more details."
            logger.warning(details)
        else:
            # Flawless victory.
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_data.name,
                library_version=library_version,
                status=LibraryManager.LibraryStatus.GOOD,
                problems=problems,
            )
            details = f"Successfully loaded Library '{library_data.name}' from JSON file at {json_path}"
            logger.info(details)

        return RegisterLibraryFromFileResultSuccess(library_name=library_data.name)

    def unload_library_from_registry_request(self, request: UnloadLibraryFromRegistryRequest) -> ResultPayload:
        try:
            LibraryRegistry.unregister_library(library_name=request.library_name)
        except Exception as e:
            details = f"Attempted to unload library '{request.library_name}'. Failed due to {e}"
            logger.error(details)
            return UnloadLibraryFromRegistryResultFailure()

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

    def _load_class_from_file(self, file_path: Path | str, class_name: str) -> type[BaseNode]:
        """Dynamically load a class from a Python file with support for hot reloading.

        Args:
            file_path: Path to the Python file
            class_name: Name of the class to load

        Returns:
            The loaded class

        Raises:
            ImportError: If the module cannot be imported
            AttributeError: If the class doesn't exist in the module
            TypeError: If the loaded class isn't a BaseNode-derived class
        """
        # Ensure file_path is a Path object
        file_path = Path(file_path)

        # Generate a unique module name
        module_name = f"dynamic_module_{file_path.name.replace('.', '_')}_{hash(str(file_path))}"

        # Check if this module is already loaded
        if module_name in sys.modules:
            # For dynamically loaded modules, we need to re-create the module
            # with a fresh spec rather than using importlib.reload

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
            except Exception as err:
                msg = f"Class '{class_name}' from module '{file_path}' failed to load with error: {err}"
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
        user_libraries_section = "app_events.on_app_initialization_complete.libraries_to_register"
        self._load_libraries_from_config_category(config_category=user_libraries_section, load_as_default_library=False)

        # Remove any missing libraries
        self._remove_missing_libraries_from_config(config_category=user_libraries_section)

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
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

    def _load_libraries_from_config_category(self, config_category: str, *, load_as_default_library: bool) -> None:
        config_mgr = GriptapeNodes.ConfigManager()
        libraries_to_register_category = config_mgr.get_config_value(config_category)

        if libraries_to_register_category is not None:
            for library_to_register in libraries_to_register_category:
                library_load_request = RegisterLibraryFromFileRequest(
                    file_path=library_to_register,
                    load_as_default_library=load_as_default_library,
                )
                GriptapeNodes.handle_request(library_load_request)

        # Print 'em all pretty
        self.print_library_load_status()

    def _remove_missing_libraries_from_config(self, config_category: str) -> None:
        # Now remove all libraries that were missing from the user's config.
        config_mgr = GriptapeNodes.ConfigManager()
        libraries_to_register_category = config_mgr.get_config_value(config_category)

        paths_to_remove = set()
        for library_path, library_info in self._library_file_path_to_info.items():
            if library_info.status == LibraryManager.LibraryStatus.MISSING:
                # Remove this file path from the config.
                paths_to_remove.add(library_path.lower())

        if paths_to_remove and libraries_to_register_category:
            libraries_to_register_category = [
                library for library in libraries_to_register_category if library.lower() not in paths_to_remove
            ]
            config_mgr.set_config_value(config_category, libraries_to_register_category)
