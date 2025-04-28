from __future__ import annotations

import importlib.util
import io
import json
import logging
import platform
import re
import subprocess
import sys
import sysconfig
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, TextIO, TypeVar, cast

from dotenv import load_dotenv
from rich.box import HEAVY_EDGE
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from xdg_base_dirs import xdg_data_home

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.app_events import (
    AppGetSessionRequest,
    AppGetSessionResultSuccess,
    AppInitializationComplete,
    AppStartSessionRequest,
    AppStartSessionResultSuccess,
    GetEngineVersionRequest,
    GetEngineVersionResultFailure,
    GetEngineVersionResultSuccess,
)
from griptape_nodes.retained_mode.events.arbitrary_python_events import (
    RunArbitraryPythonStringRequest,
    RunArbitraryPythonStringResultFailure,
    RunArbitraryPythonStringResultSuccess,
)
from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    BaseEvent,
    RequestPayload,
    ResultPayload,
)
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    DeleteFlowRequest,
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
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AlterParameterDetailsRequest,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    LoadWorkflowMetadata,
    LoadWorkflowMetadataResultSuccess,
    RegisterWorkflowRequest,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.context_manager import ContextManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
from griptape_nodes.retained_mode.managers.node_manager import NodeManager
from griptape_nodes.retained_mode.managers.object_manager import ObjectManager
from griptape_nodes.retained_mode.managers.operation_manager import OperationDepthManager
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
from griptape_nodes.retained_mode.managers.settings import WorkflowSettingsDetail
from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import (
        Parameter,
    )

load_dotenv()

T = TypeVar("T")


logger = logging.getLogger("griptape_nodes")
logger.setLevel(logging.INFO)

logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))


@dataclass
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def from_string(cls, version_string: str) -> Version | None:
        match = re.match(r"(\d+)\.(\d+)\.(\d+)", version_string)
        if match:
            major, minor, patch = map(int, match.groups())
            return cls(major, minor, patch)
        return None

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class SingletonMeta(type):
    _instances: ClassVar[dict] = {}

    def __call__(cls, *args, **kwargs) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class GriptapeNodes(metaclass=SingletonMeta):
    def __init__(self) -> None:
        # Initialize only if our managers haven't been created yet
        if not hasattr(self, "_event_manager"):
            self._event_manager = EventManager()
            self._os_manager = OSManager(self._event_manager)
            self._config_manager = ConfigManager(self._event_manager)
            self._secrets_manager = SecretsManager(self._config_manager, self._event_manager)
            self._object_manager = ObjectManager(self._event_manager)
            self._node_manager = NodeManager(self._event_manager)
            self._flow_manager = FlowManager(self._event_manager)
            self._context_manager = ContextManager(self._event_manager)
            self._library_manager = LibraryManager(self._event_manager)
            self._workflow_manager = WorkflowManager(self._event_manager)
            self._arbitrary_code_exec_manager = ArbitraryCodeExecManager(self._event_manager)
            self._operation_depth_manager = OperationDepthManager(self._config_manager)

            # Assign handlers now that these are created.
            self._event_manager.assign_manager_to_request_type(
                GetEngineVersionRequest, self.handle_engine_version_request
            )
            self._event_manager.assign_manager_to_request_type(
                AppStartSessionRequest, self.handle_session_start_request
            )
            self._event_manager.assign_manager_to_request_type(AppGetSessionRequest, self.handle_get_session_request)

    @classmethod
    def get_instance(cls) -> GriptapeNodes:
        """Helper method to get the singleton instance."""
        return cls()

    @classmethod
    def handle_request(cls, request: RequestPayload) -> ResultPayload:
        griptape_nodes_instance = GriptapeNodes.get_instance()
        event_mgr = griptape_nodes_instance._event_manager
        obj_depth_mgr = griptape_nodes_instance._operation_depth_manager
        workflow_mgr = griptape_nodes_instance._workflow_manager
        return event_mgr.handle_request(request=request, operation_depth_mgr=obj_depth_mgr, workflow_mgr=workflow_mgr)

    @classmethod
    def broadcast_app_event(cls, app_event: AppPayload) -> None:
        event_mgr = GriptapeNodes.get_instance()._event_manager
        return event_mgr.broadcast_app_event(app_event)

    @classmethod
    def get_session_id(cls) -> str | None:
        return BaseEvent._session_id

    @classmethod
    def EventManager(cls) -> EventManager:
        return GriptapeNodes.get_instance()._event_manager

    @classmethod
    def LibraryManager(cls) -> LibraryManager:
        return GriptapeNodes.get_instance()._library_manager

    @classmethod
    def ObjectManager(cls) -> ObjectManager:
        return GriptapeNodes.get_instance()._object_manager

    @classmethod
    def FlowManager(cls) -> FlowManager:
        return GriptapeNodes.get_instance()._flow_manager

    @classmethod
    def NodeManager(cls) -> NodeManager:
        return GriptapeNodes.get_instance()._node_manager

    @classmethod
    def ContextManager(cls) -> ContextManager:
        return GriptapeNodes.get_instance()._context_manager

    @classmethod
    def WorkflowManager(cls) -> WorkflowManager:
        return GriptapeNodes.get_instance()._workflow_manager

    @classmethod
    def ArbitraryCodeExecManager(cls) -> ArbitraryCodeExecManager:
        return GriptapeNodes.get_instance()._arbitrary_code_exec_manager

    @classmethod
    def ConfigManager(cls) -> ConfigManager:
        return GriptapeNodes.get_instance()._config_manager

    @classmethod
    def SecretsManager(cls) -> SecretsManager:
        return GriptapeNodes.get_instance()._secrets_manager

    @classmethod
    def OperationDepthManager(cls) -> OperationDepthManager:
        return GriptapeNodes.get_instance()._operation_depth_manager

    @classmethod
    def clear_data(cls) -> None:
        # Get canvas
        more_flows = True
        while more_flows:
            flows = GriptapeNodes.ObjectManager().get_filtered_subset(type=ControlFlow)
            found_orphan = False
            for flow_name in flows:
                try:
                    parent = GriptapeNodes.FlowManager().get_parent_flow(flow_name)
                except Exception as e:
                    raise Exception(e) from e
                if not parent:
                    event = DeleteFlowRequest(flow_name=flow_name)
                    GriptapeNodes.handle_request(event)
                    found_orphan = True
                    break
            if not flows or not found_orphan:
                more_flows = False
        if GriptapeNodes.ObjectManager()._name_to_objects:
            msg = "Failed to successfully delete all objects"
            raise ValueError(msg)

    def handle_engine_version_request(self, request: GetEngineVersionRequest) -> ResultPayload:  # noqa: ARG002
        import importlib.metadata

        try:
            engine_version_str = importlib.metadata.version("griptape_nodes")

            engine_ver = Version.from_string(engine_version_str)
            if engine_ver:
                return GetEngineVersionResultSuccess(
                    major=engine_ver.major, minor=engine_ver.minor, patch=engine_ver.patch
                )
            details = f"Attempted to get engine version. Failed because version string '{engine_version_str}' wasn't in expected major.minor.patch format."
            logger.error(details)
            return GetEngineVersionResultFailure()
        except Exception as err:
            details = f"Attempted to get engine version. Failed due to '{err}'."
            logger.error(details)
            return GetEngineVersionResultFailure()

    def handle_session_start_request(self, request: AppStartSessionRequest) -> ResultPayload:
        if BaseEvent._session_id is None:
            details = f"Session '{request.session_id}' started at {datetime.now(tz=UTC)}."
        else:
            if BaseEvent._session_id == request.session_id:
                details = f"Session '{request.session_id}' already in place. No action taken."
            else:
                details = f"Attempted to start a session with ID '{request.session_id}' but this engine instance already had a session ID `{BaseEvent._session_id}' in place. Replacing it."

            logger.info(details)

        BaseEvent._session_id = request.session_id

        # TODO(griptape): Do we want to broadcast that a session started?

        return AppStartSessionResultSuccess(request.session_id)

    def handle_get_session_request(self, _: AppGetSessionRequest) -> ResultPayload:
        return AppGetSessionResultSuccess(session_id=BaseEvent._session_id)


def create_flows_in_order(flow_name, flow_manager, created_flows, file) -> list | None:
    # If this flow is already created, we can return
    if flow_name in created_flows:
        return None

    # Get the parent of this flow
    parent = flow_manager.get_parent_flow(flow_name)

    # If there's a parent, create it first
    if parent:
        create_flows_in_order(parent, flow_manager, created_flows, file)

    # Now create this flow (only if not already created)
    if flow_name not in created_flows:
        # Here you would actually send the request and handle response
        creation_request = CreateFlowRequest(flow_name=flow_name, parent_flow_name=parent)
        code_string = f"GriptapeNodes.handle_request({creation_request})"
        file.write(code_string + "\n")
        created_flows.append(flow_name)

    return created_flows


def handle_flow_saving(file: TextIO, obj_manager: ObjectManager, created_flows: list) -> str:
    flow_manager = GriptapeNodes.get_instance()._flow_manager
    connection_request_workflows = ""
    for flow_name, flow in obj_manager.get_filtered_subset(type=ControlFlow).items():
        create_flows_in_order(flow_name, flow_manager, created_flows, file)
        # While creating flows - let's create all of our connections
        for connection in flow.connections.connections.values():
            creation_request = CreateConnectionRequest(
                source_node_name=connection.source_node.name,
                source_parameter_name=connection.source_parameter.name,
                target_node_name=connection.target_node.name,
                target_parameter_name=connection.target_parameter.name,
                initial_setup=True,
            )
            code_string = f"GriptapeNodes.handle_request({creation_request})"
            connection_request_workflows += code_string + "\n"
    return connection_request_workflows


def handle_parameter_creation_saving(node: BaseNode, values_created: dict) -> tuple[str, bool]:
    parameter_details = ""
    saved_properly = True
    for parameter in node.parameters:
        param_dict = parameter.to_dict()
        # Create the parameter, or alter it on the existing node
        if parameter.user_defined:
            param_dict["node_name"] = node.name
            param_dict["initial_setup"] = True
            creation_request = AddParameterToNodeRequest.create(**param_dict)
            code_string = f"GriptapeNodes.handle_request({creation_request})\n"
            parameter_details += code_string
        else:
            base_node_obj = type(node)(name="test")
            diff = manage_alter_details(parameter, base_node_obj)
            relevant = False
            for key in diff:
                if key in AlterParameterDetailsRequest.relevant_parameters():
                    relevant = True
                    break
            if relevant:
                diff["node_name"] = node.name
                diff["parameter_name"] = parameter.name
                diff["initial_setup"] = True
                creation_request = AlterParameterDetailsRequest.create(**diff)
                code_string = f"GriptapeNodes.handle_request({creation_request})\n"
                parameter_details += code_string
        if parameter.name in node.parameter_values or parameter.name in node.parameter_output_values:
            # SetParameterValueRequest event
            code_string = handle_parameter_value_saving(parameter, node, values_created)
            if code_string:
                code_string = code_string + "\n"
                parameter_details += code_string
            else:
                saved_properly = False
    return parameter_details, saved_properly


def handle_parameter_value_saving(parameter: Parameter, node: BaseNode, values_created: dict) -> str | None:
    """Generates code to save a parameter value for a node in a Griptape workflow.

    This function handles the process of creating code that will reconstruct and set
    parameter values for nodes. It performs the following steps:
    1. Retrieves the parameter value from the node's parameter values or output values
    2. Checks if the value has already been created in the generated code
    3. If not, generates code to reconstruct the value
    4. Creates a SetParameterValueRequest to apply the value to the node

    Args:
        parameter (Parameter): The parameter object containing metadata
        node (BaseNode): The node object that contains the parameter
        values_created (dict): Dictionary mapping value identifiers to variable names
                              that have already been created in the code

    Returns:
        str | None: Python code as a string that will reconstruct and set the parameter
                   value when executed. Returns None if the parameter has no value or
                   if the value cannot be properly represented.

    Notes:
        - Parameter output values take precedence over regular parameter values
        - For values that can be hashed, the value itself is used as the key in values_created
        - For unhashable values, the object's id is used as the key
        - The function will reuse already created values to avoid duplication
    """
    value = None
    is_output = False
    if parameter.name in node.parameter_values:
        value = node.get_parameter_value(parameter.name)
    # Output values are more important
    if parameter.name in node.parameter_output_values:
        value = node.parameter_output_values[parameter.name]
        is_output = True
    if value is not None:
        try:
            hash(value)
            value_id = value
        except TypeError:
            value_id = id(value)
        if value_id in values_created:
            var_name = values_created[value_id]
            # We've already created this object. we're all good.
            return f"GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='{parameter.name}', node_name='{node.name}', value={var_name}, initial_setup=True, is_output={is_output}))"
        # Set it up as a object in the code
        imports = []
        var_name = f"{node.name}_{parameter.name}_value"
        values_created[value_id] = var_name
        reconstruction_code = _convert_value_to_str_representation(var_name, value, imports)
        # If it doesn't have a custom __str__, convert to dict if possible
        if reconstruction_code != "":
            # Add the request handling code
            final_code = (
                reconstruction_code
                + f"GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='{parameter.name}', node_name='{node.name}', value={var_name}, initial_setup=True, is_output={is_output}))"
            )
            # Combine imports and code
            import_statements = ""
            if imports:
                import_statements = "\n".join(list(set(imports))) + "\n\n"  # Remove duplicates with set()
            return import_statements + final_code
    return None


def _convert_value_to_str_representation(var_name: str, value: Any, imports: list) -> str:
    """Converts a Python value to its string representation as executable code.

    This function generates Python code that can recreate the given value
    when executed. It handles different types of values with specific strategies:
    - Objects with a 'to_dict' method: Uses _create_object_in_file for reconstruction
    - Basic Python types: Uses their repr representation
    - If not representable: Returns empty string

    Args:
        var_name (str): The variable name to assign the value to in the generated code
        value (Any): The Python value to convert to code
        imports (list): List to which any required import statements will be appended

    Returns:
        str: Python code as a string that will reconstruct the value when executed.
             Returns empty string if the value cannot be properly represented.
    """
    reconstruction_code = ""
    # If it doesn't have a custom __str__, convert to dict if possible
    if hasattr(value, "to_dict") and callable(value.to_dict):
        # For objects with to_dict method
        reconstruction_code = _create_object_in_file(value, var_name, imports)
        return reconstruction_code
    if isinstance(value, (int, float, str, bool)) or value is None:
        # For basic types, use repr to create a literal
        return f"{var_name} = {value!r}\n"
    if isinstance(value, (list, dict, tuple, set)):
        reconstruction_code = _convert_container_to_str_representation(var_name, value, imports, type(value))
        return reconstruction_code
    return ""


def _convert_container_to_str_representation(var_name: str, value: Any, imports: list, value_type: type) -> str:
    """Creates code to reconstruct a container type (list, dict, tuple, set) with its elements.

    Args:
        var_name (str): The variable name to assign the container to
        value (Any): The container value to convert to code
        imports (list): List to which any required import statements will be appended
        value_type (type): The type of container (list, dict, tuple, or set)

    Returns:
        str: Python code as a string that will reconstruct the container
    """
    # Get the initialization brackets from an empty container
    empty_container = value_type()
    init_brackets = repr(empty_container)
    # Initialize the container
    code = f"{var_name} = {init_brackets}\n"
    temp_var_base = f"{var_name}_item"
    if value_type is dict:
        # Process dictionary items
        for i, (k, v) in enumerate(value.items()):
            temp_var = f"{temp_var_base}_{i}"
            # Convert the value to code
            value_code = _convert_value_to_str_representation(temp_var, v, imports)
            if value_code:
                code += value_code
                code += f"{var_name}[{k!r}] = {temp_var}\n"
            else:
                code += f"{var_name}[{k!r}] = {v!r}\n"
    else:
        # Process sequence items (list, tuple, set)
        # For immutable types like tuple and set, we need to build a list first
        for i, item in enumerate(value):
            temp_var = f"{temp_var_base}_{i}"
            # Convert the item to code
            item_code = _convert_value_to_str_representation(temp_var, item, imports)
            if item_code != "":
                code += item_code
                code += f"{var_name}.append({temp_var})\n"
            else:
                code += f"{var_name}.append({item!r})\n"
        # Convert the list to the final type if needed
        if value_type in (tuple, set):
            code += f"{var_name} = {value_type.__name__}({var_name})\n"
    return code


def _create_object_in_file(value: Any, var_name: str, imports: list) -> str:
    """Creates Python code to reconstruct an object from its dictionary representation and adds necessary import statements.

    Args:
        value (Any): The object to be serialized into Python code
        var_name (str): The name of the variable to assign the object to in the generated code
        imports (list): List to which import statements will be appended

    Returns:
        str: Python code string that reconstructs the object when executed
             Returns empty string if object cannot be properly reconstructed

    Notes:
        - The function assumes the object has a 'to_dict()' method to serialize it. It is only called if the object does have that method.
        - For class instances, it will add appropriate import statements to 'imports'
        - The generated code will create a dictionary representation first, then
          reconstruct the object using a 'from_dict' class method
    """
    obj_dict = value.to_dict()
    reconstruction_code = f"{var_name} = {obj_dict!r}\n"
    # If we know the class, we can reconstruct it and add import
    if hasattr(value, "__class__"):
        class_name = value.__class__.__name__
        module_name = value.__class__.__module__
        if module_name != "builtins":
            imports.append(f"from {module_name} import {class_name}")
        reconstruction_code += f"{var_name} = {class_name}.from_dict({var_name})\n"
        return reconstruction_code
    return ""


def manage_alter_details(parameter: Parameter, base_node_obj: BaseNode) -> dict:
    base_param = base_node_obj.get_parameter_by_name(parameter.name)
    if base_param:
        diff = base_param.equals(parameter)
    else:
        return vars(parameter)
    return diff


class ArbitraryCodeExecManager:
    def __init__(self, event_manager: EventManager) -> None:
        event_manager.assign_manager_to_request_type(
            RunArbitraryPythonStringRequest, self.on_run_arbitrary_python_string_request
        )

    def on_run_arbitrary_python_string_request(self, request: RunArbitraryPythonStringRequest) -> ResultPayload:
        try:
            string_buffer = io.StringIO()
            with redirect_stdout(string_buffer):
                python_output = exec(request.python_string)  # noqa: S102

            captured_output = string_buffer.getvalue()
            result = RunArbitraryPythonStringResultSuccess(python_output=captured_output)
        except Exception as e:
            python_output = f"ERROR: {e}"
            result = RunArbitraryPythonStringResultFailure(python_output=python_output)

        return result


class LibraryManager:
    class LibraryStatus(StrEnum):
        GOOD = "GOOD"  # No errors detected during loading. Registered.
        FLAWED = "FLAWED"  # Some errors detected, but recoverable. Registered.
        UNUSABLE = "UNUSABLE"  # Errors detected and not recoverable. Not registered.
        MISSING = "MISSING"  # File not found. Not registered.

    @dataclass
    class LibraryInfo:
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
        library_file_paths = GriptapeNodes.LibraryManager().get_libraries_attempted_to_load()
        library_infos = []
        for library_file_path in library_file_paths:
            library_info = GriptapeNodes.LibraryManager().get_library_info_for_attempted_load(library_file_path)
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
        table.add_column("Version", style="green")
        table.add_column("File Path", style="cyan")
        table.add_column("Problems", style="yellow")

        # Status emojis mapping
        status_emoji = {
            LibraryManager.LibraryStatus.GOOD: "✅",
            LibraryManager.LibraryStatus.FLAWED: "🚨",
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
            emoji = status_emoji.get(lib_info.status, "ERR: Unknown/Unexpected Library Status")
            name = lib_info.library_name if lib_info.library_name else "*UNKNOWN*"
            library_name = f"{emoji} {name}"

            library_version = lib_info.library_version
            if library_version:
                version_str = str(library_version)
            else:
                version_str = "*UNKNOWN*"

            # Problems column - format with numbers if there's more than one
            if not lib_info.problems:
                problems = "<none>"
            elif len(lib_info.problems) == 1:
                problems = lib_info.problems[0]
            else:
                # Number the problems when there's more than one
                problems = "\n".join([f"{j + 1}. {problem}" for j, problem in enumerate(lib_info.problems)])

            # Add the row to the table
            table.add_row(library_name, version_str, file_path_text, problems)

        # Create a panel containing the table
        panel = Panel(table, title="Library Information", border_style="blue")

        # Display the panel
        console.print(panel)

    def get_libraries_attempted_to_load(self) -> list[str]:
        return list(self._library_file_path_to_info.keys())

    def get_library_info_for_attempted_load(self, library_file_path: str) -> LibraryInfo:
        return self._library_file_path_to_info[library_file_path]

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
                problems=["Library could not be found."],
            )
            details = f"Attempted to load Library JSON file. Failed because no file could be found at the specified path: {json_path}"
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Load the JSON
        try:
            with json_path.open("r") as f:
                library_data = json.load(f)
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

        # Extract library information
        try:
            library_name: str = library_data["name"]
            library_metadata = library_data["metadata"]
            nodes_metadata = library_data.get("nodes", [])
        except KeyError as err:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=None,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[f"Exception occurred when attempting to load required fields in the library: {err}."],
            )
            details = f"Attempted to load Library JSON file from '{json_path}'. Failed because it was missing required field in library metadata: {err}"
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()
        except Exception as err:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=None,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[f"Exception occurred when attempting to load the library: {err}."],
            )
            details = (
                f"Attempted to load Library JSON file from '{json_path}'. Failed because an exception occurred: {err}"
            )
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Get the library version.
        library_version_key = "library_version"
        if library_version_key not in library_metadata:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_name,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[f"Library was missing the '{library_version_key}' in its metadata section."],
            )
            details = f"Attempted to load Library '{library_name}' JSON file from '{json_path}'. Failed because it was missing the '{library_version_key}' in its metadata section."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Make sure the version string is copacetic.
        library_version = library_metadata[library_version_key]
        if library_version is None:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_name,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[
                    f"Library's version string '{library_metadata[library_version_key]}' wasn't valid. Must be in major.minor.patch format."
                ],
            )
            details = f"Attempted to load Library '{library_name}' JSON file from '{json_path}'. Failed because version string '{library_metadata[library_version_key]}' wasn't valid. Must be in major.minor.patch format."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        categories = library_data.get("categories", None)

        # Get the directory containing the JSON file to resolve relative paths
        base_dir = json_path.parent.absolute()
        # Add the directory to the Python path to allow for relative imports
        sys.path.insert(0, str(base_dir))

        # Create or get the library
        try:
            # Try to create a new library
            library = LibraryRegistry.generate_new_library(
                name=library_name,
                mark_as_default_library=request.load_as_default_library,
                categories=categories,
            )

        except KeyError as err:
            # Library already exists
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_name,
                library_version=library_version,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[
                    "Failed because a library with this name was already registered. Check the Settings to ensure duplicate libraries are not being loaded."
                ],
            )

            details = f"Attempted to load Library JSON file from '{json_path}'. Failed because a Library '{library_name}' already exists. Error: {err}."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Install node library dependencies
        try:
            dependencies = library_metadata.get("dependencies", [])
            site_packages = None
            if dependencies:
                pip_install_flags = library_metadata.get("pip_install_flags", [])
                # Create a virtual environment for the library
                python_version = platform.python_version()
                library_venv_path = (
                    xdg_data_home()
                    / "griptape_nodes"
                    / "venvs"
                    / python_version
                    / library_name.replace(" ", "_").strip()
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
                        *dependencies,
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
                library_name=library_name,
                library_version=library_version,
                status=LibraryManager.LibraryStatus.UNUSABLE,
                problems=[f"Failed to create the library: {e}"],
            )
            details = (
                f"Attempted to load Library JSON file from '{json_path}'. Failed when installing dependencies: {e}."
            )
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Update library metadata
        library._metadata = library_metadata

        problems = []
        any_successes = False
        # Process each node in the metadata
        for node_meta in nodes_metadata:
            try:
                class_name = node_meta["class_name"]
            except Exception as err:
                problems.append(f"Failed to load node with error: {err}")
                details = (
                    f"Attempted to load node from Library at '{json_path}'. Failed because an exception occurred: {err}"
                )
                logger.error(details)
                continue  # SKIP IT
            try:
                node_file_path = node_meta["file_path"]
                node_metadata = node_meta.get("metadata", {})
            except Exception as err:
                problems.append(f"Failed to load node '{class_name}' with error: {err}")
                details = f"Attempted to load node '{class_name}' from Library at '{json_path}'. Failed because an exception occurred: {err}"
                logger.error(details)
                continue  # SKIP IT

            # Resolve relative path to absolute path
            node_file_path = Path(node_file_path)
            if not node_file_path.is_absolute():
                node_file_path = base_dir / node_file_path

            try:
                # Dynamically load the module containing the node class
                node_class = self._load_class_from_file(node_file_path, class_name)
            except Exception as err:
                problems.append(f"Failed to load node '{class_name}' from '{node_file_path}' with error: {err}")
                details = f"Attempted to load node '{class_name}' from '{node_file_path}'. Failed because an exception occurred: {err}"
                logger.error(details)
                continue  # SKIP IT

            try:
                # Register the node type with the library
                forensics_string = library.register_new_node_type(node_class, metadata=node_metadata)
                if forensics_string is not None:
                    problems.append(forensics_string)
            except Exception as err:
                problems.append(f"Failed to register node '{class_name}' from '{node_file_path}' with error: {err}")
                details = f"Attempted to load node '{class_name}' from '{node_file_path}'. Failed because an exception occurred: {err}"
                logger.error(details)
                continue  # SKIP IT

            # If we got here, at least one node came in.
            any_successes = True

        if not any_successes:
            self._library_file_path_to_info[file_path] = LibraryManager.LibraryInfo(
                library_path=file_path,
                library_name=library_name,
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
                library_name=library_name,
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
                library_name=library_name,
                library_version=library_version,
                status=LibraryManager.LibraryStatus.GOOD,
                problems=problems,
            )
            details = f"Successfully loaded Library '{library_name}' from JSON file at {json_path}"
            logger.info(details)

        return RegisterLibraryFromFileResultSuccess(library_name=library_name)

    def unload_library_from_registry_request(self, request: UnloadLibraryFromRegistryRequest) -> ResultPayload:
        try:
            LibraryRegistry.unregister_library(library_name=request.library_name)
        except Exception as e:
            details = f"Attempted to unload library '{request.library_name}'. Failed due to {e}"
            logger.error(details)
            return UnloadLibraryFromRegistryResultFailure()

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

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        # App just got init'd. See if there are library JSONs to load!
        self.load_all_libraries_from_config()

        # See if there are workflow JSONs to load!
        default_workflow_section = "app_events.on_app_initialization_complete.workflows_to_register"
        self._register_workflows_from_config(config_section=default_workflow_section)

    def _load_libraries_from_config_category(self, config_category: str, load_as_default_library: bool) -> None:  # noqa: FBT001
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

    # TODO(griptape): Move to WorkflowManager
    def _register_workflows_from_config(self, config_section: str) -> None:
        config_mgr = GriptapeNodes.ConfigManager()
        workflows_to_register = config_mgr.get_config_value(config_section)
        if workflows_to_register is not None:
            for workflow_to_register in workflows_to_register:
                try:
                    workflow_detail = WorkflowSettingsDetail(
                        file_name=workflow_to_register["file_name"],
                        is_griptape_provided=workflow_to_register["is_griptape_provided"],
                    )
                except Exception as err:
                    err_str = f"Error attempting to get info about workflow to register '{workflow_to_register}': {err}. SKIPPING IT."
                    logger.error(err_str)
                    continue

                # Adjust path depending on if it's a Griptape-provided workflow or a user one.
                if workflow_detail.is_griptape_provided:
                    final_file_path = xdg_data_home().joinpath(workflow_detail.file_name)
                else:
                    final_file_path = config_mgr.workspace_path.joinpath(workflow_detail.file_name)

                # Attempt to extract the metadata out of the workflow.
                load_metadata_request = LoadWorkflowMetadata(file_name=str(final_file_path))
                load_metadata_result = GriptapeNodes.WorkflowManager().on_load_workflow_metadata_request(
                    load_metadata_request
                )
                if not load_metadata_result.succeeded():
                    # SKIP IT
                    continue

                try:
                    successful_metadata_result = cast("LoadWorkflowMetadataResultSuccess", load_metadata_result)
                except Exception as err:
                    err_str = f"Error attempting to get info about workflow to register '{final_file_path}': {err}. SKIPPING IT."
                    logger.error(err_str)
                    continue

                workflow_metadata = successful_metadata_result.metadata

                # Prepend the image paths appropriately.
                if workflow_metadata.image is not None:
                    if workflow_detail.is_griptape_provided:
                        workflow_metadata.image = workflow_metadata.image
                    else:
                        workflow_metadata.image = str(config_mgr.workspace_path.joinpath(workflow_metadata.image))

                # Register it as a success.
                workflow_register_request = RegisterWorkflowRequest(
                    metadata=workflow_metadata, file_name=str(final_file_path)
                )
                GriptapeNodes.handle_request(workflow_register_request)

        # Print it all out nicely.
        GriptapeNodes.WorkflowManager().print_workflow_load_status()


def __getattr__(name) -> logging.Logger:
    """Convenience function so that node authors only need to write 'logger.debug()'."""
    if name == "logger":
        return logger
    msg = f"module '{__name__}' has no attribute '{name}'"
    raise AttributeError(msg)
