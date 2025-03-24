import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from re import Pattern
from typing import Any, TextIO, TypeVar, cast

from dotenv import load_dotenv

from griptape_nodes.exe_types.core_types import Parameter, ParameterControlType, ParameterMode
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import NodeBase, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.node_library.script_registry import ScriptRegistry
from griptape_nodes.retained_mode.events.app_events import (
    AppExecutionEvent,
    AppInitializationComplete,
    GetEngineVersion_Request,
    GetEngineVersionResult_Failure,
    GetEngineVersionResult_Success,
)
from griptape_nodes.retained_mode.events.arbitrary_python_events import (
    RunArbitraryPythonStringRequest,
    RunArbitraryPythonStringResult_Failure,
    RunArbitraryPythonStringResult_Success,
)
from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    EventBase,
    RequestPayload,
    ResultPayload,
    ResultPayload_Failure,
)
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    CreateConnectionResult_Failure,
    CreateConnectionResult_Success,
    DeleteConnectionRequest,
    DeleteConnectionResult_Failure,
    DeleteConnectionResult_Success,
    IncomingConnection,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResult_Failure,
    ListConnectionsForNodeResult_Success,
    OutgoingConnection,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CancelFlowRequest,
    CancelFlowResult_Failure,
    CancelFlowResult_Success,
    ContinueExecutionStepRequest,
    ContinueExecutionStepResult_Failure,
    ContinueExecutionStepResult_Success,
    GetFlowStateRequest,
    GetFlowStateResult_Failure,
    GetFlowStateResult_Success,
    GetIsFlowRunningRequest,
    GetIsFlowRunningResult_Failure,
    GetIsFlowRunningResult_Success,
    ResolveNodeRequest,
    ResolveNodeResult_Failure,
    ResolveNodeResult_Success,
    SingleExecutionStepRequest,
    SingleExecutionStepResult_Failure,
    SingleExecutionStepResult_Success,
    SingleNodeStepRequest,
    SingleNodeStepResult_Failure,
    SingleNodeStepResult_Success,
    StartFlowRequest,
    StartFlowResult_Failure,
    StartFlowResult_Success,
    UnresolveFlowRequest,
    UnresolveFlowResult_Failure,
    UnresolveFlowResult_Success,
)
from griptape_nodes.retained_mode.events.validation_events import (
    ValidateFlowDependenciesRequest,
    ValidateFlowDependenciesResult_Failure,
    ValidateFlowDependenciesResult_Success,
    ValidateNodeDependenciesRequest,
    ValidateNodeDependenciesResult_Failure,
    ValidateNodeDependenciesResult_Success
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    CreateFlowResult_Failure,
    CreateFlowResult_Success,
    DeleteFlowRequest,
    DeleteFlowResult_Failure,
    DeleteFlowResult_Success,
    ListFlowsInFlowRequest,
    ListFlowsInFlowResult_Failure,
    ListFlowsInFlowResult_Success,
    ListNodesInFlowRequest,
    ListNodesInFlowResult_Failure,
    ListNodesInFlowResult_Success,
)
from griptape_nodes.retained_mode.events.library_events import (
    GetAllInfoForAllLibrariesRequest,
    GetAllInfoForAllLibrariesResult_Failure,
    GetAllInfoForAllLibrariesResult_Success,
    GetAllInfoForLibraryRequest,
    GetAllInfoForLibraryResult_Failure,
    GetAllInfoForLibraryResult_Success,
    GetLibraryMetadataRequest,
    GetLibraryMetadataResult_Failure,
    GetLibraryMetadataResult_Success,
    GetNodeMetadataFromLibraryRequest,
    GetNodeMetadataFromLibraryResult_Failure,
    GetNodeMetadataFromLibraryResult_Success,
    ListCategoriesInLibraryRequest,
    ListCategoriesInLibraryResult_Failure,
    ListCategoriesInLibraryResult_Success,
    ListNodeTypesInLibraryRequest,
    ListNodeTypesInLibraryResult_Failure,
    ListNodeTypesInLibraryResult_Success,
    ListRegisteredLibrariesRequest,
    ListRegisteredLibrariesResult_Success,
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromFileResult_Failure,
    RegisterLibraryFromFileResult_Success,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResult_Failure,
    CreateNodeResult_Success,
    DeleteNodeRequest,
    DeleteNodeResult_Failure,
    DeleteNodeResult_Success,
    GetAllNodeInfoRequest,
    GetAllNodeInfoResult_Failure,
    GetAllNodeInfoResult_Success,
    GetNodeMetadataRequest,
    GetNodeMetadataResult_Failure,
    GetNodeMetadataResult_Success,
    GetNodeResolutionStateRequest,
    GetNodeResolutionStateResult_Failure,
    GetNodeResolutionStateResult_Success,
    ListParametersOnNodeRequest,
    ListParametersOnNodeResult_Failure,
    ListParametersOnNodeResult_Success,
    ParameterInfoValue,
    SetNodeMetadataRequest,
    SetNodeMetadataResult_Failure,
    SetNodeMetadataResult_Success,
)
from griptape_nodes.retained_mode.events.object_events import (
    RenameObjectRequest,
    RenameObjectResult_Failure,
    RenameObjectResult_Success,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AddParameterToNodeResult_Failure,
    AddParameterToNodeResult_Success,
    AlterParameterDetailsRequest,
    AlterParameterDetailsResult_Failure,
    AlterParameterDetailsResult_Success,
    GetParameterDetailsRequest,
    GetParameterDetailsResult_Failure,
    GetParameterDetailsResult_Success,
    GetParameterValueRequest,
    GetParameterValueResult_Failure,
    GetParameterValueResult_Success,
    RemoveParameterFromNodeRequest,
    RemoveParameterFromNodeResult_Failure,
    RemoveParameterFromNodeResult_Success,
    SetParameterValueRequest,
    SetParameterValueResult_Failure,
    SetParameterValueResult_Success,
)
from griptape_nodes.retained_mode.events.script_events import (
    DeleteScriptRequest,
    DeleteScriptResult_Failure,
    DeleteScriptResult_Success,
    ListAllScriptsRequest,
    ListAllScriptsResult_Failure,
    ListAllScriptsResult_Success,
    RegisterScriptRequest,
    RegisterScriptResult_Failure,
    RegisterScriptResult_Success,
    RunScriptFromRegistryRequest,
    RunScriptFromRegistryResult_Failure,
    RunScriptFromRegistryResult_Success,
    RunScriptFromScratchRequest,
    RunScriptFromScratchResult_Failure,
    RunScriptFromScratchResult_Success,
    RunScriptWithCurrentStateRequest,
    RunScriptWithCurrentStateResult_Failure,
    RunScriptWithCurrentStateResult_Success,
    SaveSceneRequest,
    SaveSceneResult_Failure,
    SaveSceneResult_Success,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.operation_manager import OperationDepthManager
from griptape_nodes.retained_mode.managers.os_manager import OSManager

load_dotenv()

T = TypeVar("T")


class SingletonMeta(type):
    _instances = {}

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
            self._object_manager = ObjectManager(self._event_manager)
            self._node_manager = NodeManager(self._event_manager)
            self._flow_manager = FlowManager(self._event_manager)
            self._library_manager = LibraryManager(self._event_manager)
            self._script_manager = ScriptManager(self._event_manager)
            self._arbitrary_code_exec_manager = ArbitraryCodeExecManager(self._event_manager)
            self._operation_depth_manager = OperationDepthManager(self._config_manager)

            # Assign handlers now that these are created.
            self._event_manager.assign_manager_to_request_type(
                GetEngineVersion_Request, self.handle_engine_version_request
            )

    @classmethod
    def get_instance(cls) -> "GriptapeNodes":
        """Helper method to get the singleton instance."""
        return cls()

    @classmethod
    def handle_request(cls, request: RequestPayload) -> ResultPayload:
        griptape_nodes_instance = GriptapeNodes.get_instance()
        event_mgr = griptape_nodes_instance._event_manager
        obj_depth_mgr = griptape_nodes_instance._operation_depth_manager
        return event_mgr.handle_request(request=request, operation_depth_mgr=obj_depth_mgr)

    @classmethod
    def broadcast_app_event(cls, app_event: AppPayload) -> None:
        event_mgr = GriptapeNodes.get_instance()._event_manager
        return event_mgr.broadcast_app_event(app_event)

    @classmethod
    def EventManager(cls) -> EventManager:
        return GriptapeNodes.get_instance()._event_manager

    @classmethod
    def ObjectManager(cls) -> "ObjectManager":
        return GriptapeNodes.get_instance()._object_manager

    @classmethod
    def FlowManager(cls) -> "FlowManager":
        return GriptapeNodes.get_instance()._flow_manager

    @classmethod
    def NodeManager(cls) -> "NodeManager":
        return GriptapeNodes.get_instance()._node_manager

    @classmethod
    def ScriptManager(cls) -> "ScriptManager":
        return GriptapeNodes.get_instance()._script_manager

    @classmethod
    def ArbitraryCodeExecManager(cls) -> "ArbitraryCodeExecManager":
        return GriptapeNodes.get_instance()._arbitrary_code_exec_manager

    @classmethod
    def ConfigManager(cls) -> "ConfigManager":
        return GriptapeNodes.get_instance()._config_manager

    @classmethod
    def OperationDepthManager(cls) -> "OperationDepthManager":
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

    def handle_engine_version_request(self, request: GetEngineVersion_Request) -> ResultPayload:  # noqa: ARG002
        import importlib.metadata

        try:
            engine_version_str = importlib.metadata.version("griptape_nodes")

            match = re.match(r"(\d+)\.(\d+)\.(\d+)", engine_version_str)
            if match:
                major, minor, patch = map(int, match.groups())
                return GetEngineVersionResult_Success(major=major, minor=minor, patch=patch)
            details = f"Attempted to get engine version. Failed because version string '{engine_version_str}' wasn't in expected major.minor.patch format."
            print(details)  # TODO(griptape): Move to Log
            return GetEngineVersionResult_Failure()
        except Exception as err:
            details = f"Attempted to get engine version. Failed due to '{err}'."
            print(details)  # TODO(griptape): Move to Log
            return GetEngineVersionResult_Failure()


OBJ_TYPE = TypeVar("OBJ_TYPE")


class ObjectManager:
    _name_to_objects: dict[str, object]

    def __init__(self, _event_manager: EventManager) -> None:
        self._name_to_objects = {}
        _event_manager.assign_manager_to_request_type(
            request_type=RenameObjectRequest, callback=self.on_rename_object_request
        )

    def on_rename_object_request(self, request: RenameObjectRequest) -> ResultPayload:
        # Does the source object exist?
        source_obj = self.attempt_get_object_by_name(request.object_name)
        if source_obj is None:
            details = f"Attempted to rename object '{request.object_name}', but no object of that name could be found."
            print(details)  # TODO(griptape): Move to Log
            return RenameObjectResult_Failure(next_available_name=None)

        # Is there a collision?
        requested_name_obj = self.attempt_get_object_by_name(request.requested_name)
        if requested_name_obj is None:
            final_name = request.requested_name
        else:
            # Collision. Decide what to do.
            next_name = self.generate_name_for_object(
                type_name=source_obj.__class__.__name__, requested_name=request.requested_name
            )

            # Will the requester allow us to use the next closest name available?
            if not request.allow_next_closest_name_available:
                # Not allowed to use it :(
                # Fail it but be nice and offer the next name that WOULD HAVE been available.
                details = f"Attempted to rename object '{request.object_name}' to '{request.requested_name}'. Failed because another object of that name exists. Next available name would have been '{next_name}'."
                print(details)  # TODO(griptape): Move to Log
                return RenameObjectResult_Failure(next_available_name=next_name)
            # We'll use the next available name.
            final_name = next_name

        # Let the object's manager know. TODO(griptape): find a better way than a bunch of special cases.
        match source_obj:
            case ControlFlow():
                GriptapeNodes.FlowManager().handle_flow_rename(old_name=request.object_name, new_name=final_name)
            case NodeBase():
                GriptapeNodes.NodeManager().handle_node_rename(old_name=request.object_name, new_name=final_name)
            case _:
                details = f"Attempted to rename an object named '{request.object_name}', but that object wasn't of a type supported for rename."
                print(details)  # TODO(griptape): Move to Log
                return RenameObjectResult_Failure(next_available_name=None)

        # Update the object table.
        self._name_to_objects[final_name] = source_obj
        del self._name_to_objects[request.object_name]

        details = f"Successfully renamed object '{request.object_name}' to '{final_name}`."
        if final_name != request.requested_name:
            details += " WARNING: Originally requested the name '{request.requested_name}', but that was taken."
        print(details)  # TODO(griptape): Move to Log
        return RenameObjectResult_Success(final_name=final_name)

    def get_filtered_subset(
        self,
        name: str | Pattern | None = None,
        type: type[OBJ_TYPE] | None = None,  # noqa: A002
    ) -> dict[str, OBJ_TYPE]:
        """Filter a dictionary by key pattern and/or value type.

        Args:
            name: A regex pattern string or compiled pattern to match keys
            type: A type to match values

        Returns:
            A new filtered dictionary containing only matching key-value pairs
        """
        result = {}

        # Compile pattern if it's a string
        if name and isinstance(name, str):
            name = re.compile(name)

        for key, value in self._name_to_objects.items():
            # Check key pattern if provided
            key_match = True
            if name:
                key_match = bool(name.search(key))

            # Check value type if provided
            value_match = True
            if type:
                value_match = isinstance(value, type)

            # Add to result if both conditions match
            if key_match and value_match:
                result[key] = value

        return result

    def generate_name_for_object(self, type_name: str, requested_name: str | None = None) -> str:
        # Now ensure that we're giving a valid unique name. Here are the rules:
        # 1. If no name was requested, use the type name + first free integer.
        # 2. If a name was requested and no collision, use it as-is.
        # 3. If a name was requested and there IS a collision, check:
        #    a. If name ends in a number, find the FIRST prefix + integer value that isn't a collision.
        #    b. If name does NOT end in a number, use the name + first free integer.

        # We are going in with eyes open that the collision testing is inefficient.
        name_to_return = None
        incremental_prefix = ""

        if requested_name is None:
            # 1. If no name was requested, use the type name + first free integer.
            incremental_prefix = f"{type_name}_"
        elif requested_name not in self._name_to_objects:
            # 2. If a name was requested and no collision, use it as-is.
            name_to_return = requested_name
        else:
            # 3. If a name was requested and there IS a collision, check:
            pattern_match = re.search(r"\d+$", requested_name)
            if pattern_match is not None:
                #    a. If name ends in a number, find the FIRST prefix + integer value that isn't a collision.
                # Ends in a number. Find the FIRST prefix + integer value that isn't a collision.
                start = pattern_match.start()
                incremental_prefix = requested_name[:start]
            else:
                #    b. If name does NOT end in a number, use the name + first free integer.
                incremental_prefix = f"{requested_name}_"

        if name_to_return is None:
            # Do the incremental walk.
            curr_idx = 1
            done = False
            while not done:
                test_name = f"{incremental_prefix}{curr_idx}"
                if test_name not in self._name_to_objects:
                    # Found it.
                    name_to_return = test_name
                    done = True
                else:
                    # Keep going.
                    curr_idx += 1

        if name_to_return is None:
            msg = "Failed to generate a unique name for the object."
            raise ValueError(msg)

        return name_to_return

    def add_object_by_name(self, name: str, obj: object) -> None:
        if name in self._name_to_objects:
            msg = f"Attempted to add an object with name '{name}' but an object with that name already exists. The Object Manager is sacrosanct in this regard."
            raise ValueError(msg)
        self._name_to_objects[name] = obj

    def get_object_by_name(self, name: str) -> object:
        return self._name_to_objects[name]

    def has_object_with_name(self, name: str) -> bool:
        has_it = name in self._name_to_objects
        return has_it

    def attempt_get_object_by_name(self, name: str) -> Any | None:
        return self._name_to_objects.get(name)

    def attempt_get_object_by_name_as_type(self, name: str, cast_type: type[T]) -> T | None:
        obj = self.attempt_get_object_by_name(name)
        if obj is not None and isinstance(obj, cast_type):
            return obj
        return None

    def del_obj_by_name(self, name: str) -> None:
        del self._name_to_objects[name]


class FlowManager:
    _name_to_parent_name: dict[str, str | None]

    def __init__(self, event_manager: EventManager) -> None:
        event_manager.assign_manager_to_request_type(CreateFlowRequest, self.on_create_flow_request)
        event_manager.assign_manager_to_request_type(DeleteFlowRequest, self.on_delete_flow_request)
        event_manager.assign_manager_to_request_type(ListNodesInFlowRequest, self.on_list_nodes_in_flow_request)
        event_manager.assign_manager_to_request_type(ListFlowsInFlowRequest, self.on_list_flows_in_flow_request)
        event_manager.assign_manager_to_request_type(CreateConnectionRequest, self.on_create_connection_request)
        event_manager.assign_manager_to_request_type(DeleteConnectionRequest, self.on_delete_connection_request)
        event_manager.assign_manager_to_request_type(StartFlowRequest, self.on_start_flow_request)
        event_manager.assign_manager_to_request_type(SingleNodeStepRequest, self.on_single_node_step_request)
        event_manager.assign_manager_to_request_type(SingleExecutionStepRequest, self.on_single_execution_step_request)
        event_manager.assign_manager_to_request_type(
            ContinueExecutionStepRequest, self.on_continue_execution_step_request
        )
        event_manager.assign_manager_to_request_type(CancelFlowRequest, self.on_cancel_flow_request)
        event_manager.assign_manager_to_request_type(UnresolveFlowRequest, self.on_unresolve_flow_request)

        event_manager.assign_manager_to_request_type(GetFlowStateRequest, self.on_get_flow_state_request)
        event_manager.assign_manager_to_request_type(GetIsFlowRunningRequest, self.on_get_is_flow_running_request)
        event_manager.assign_manager_to_request_type(ValidateFlowDependenciesRequest, self.on_validate_flow_dependencies_request)
        # events that happen after a flow is ran
        event_manager.add_listener_to_app_event(AppExecutionEvent, self.on_app_execution_event)

        self._name_to_parent_name = {}

    def get_parent_flow(self, flow_name: str) -> str | None:
        if flow_name in self._name_to_parent_name:
            return self._name_to_parent_name[flow_name]
        msg = f"Flow with name {flow_name} doesn't exist"
        raise ValueError(msg)

    def does_canvas_exist(self) -> bool:
        """Determines if there is already an existing flow with no parent flow.Returns True if there is an existing flow with no parent flow.Return False if there is no existing flow with no parent flow."""
        return any([parent is None for parent in self._name_to_parent_name.values()])  # noqa: C419

    def on_create_flow_request(self, request: CreateFlowRequest) -> ResultPayload:
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        # Who is the parent?
        parent_name = request.parent_flow_name

        parent = obj_mgr.attempt_get_object_by_name_as_type(parent_name, ControlFlow)
        if parent_name is None:
            # We're trying to create the canvas. Ensure that parent does NOT already exist.
            if self.does_canvas_exist():
                details = "Attempted to create a Flow as the Canvas (top-level Flow with no parents), but the Canvas already exists."
                print(details)  # TODO(griptape): Move to Log
                result = CreateFlowResult_Failure()
                return result
        # That parent exists, right?
        elif parent is None:
            details = f"Attempted to create a Flow with a parent '{request.parent_flow_name}', but no parent with that name could be found."
            print(details)  # TODO(griptape): Move to Log

            result = CreateFlowResult_Failure()

            return result

        # Create it.
        final_flow_name = obj_mgr.generate_name_for_object(type_name="ControlFlow", requested_name=request.flow_name)
        flow = ControlFlow()
        obj_mgr.add_object_by_name(name=final_flow_name, obj=flow)
        self._name_to_parent_name[final_flow_name] = parent_name

        # Success
        details = f"Successfully created Flow '{final_flow_name}'."
        if (request.flow_name is not None) and (final_flow_name != request.flow_name):
            details = f"{details} WARNING: Had to rename from original Flow requested '{request.flow_name}' as an object with this name already existed."

        print(details)  # TODO(griptape): Move to Log
        result = CreateFlowResult_Success(flow_name=final_flow_name)
        return result

    def on_delete_flow_request(self, request: DeleteFlowRequest) -> ResultPayload:
        # Does this Flow even exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(request.flow_name, ControlFlow)
        if flow is None:
            details = f"Attempted to delete Flow '{request.flow_name}', but no Flow with that name could be found."
            print(details)  # TODO(griptape): Move to Log
            result = DeleteFlowResult_Failure()
            return result

        # Delete all child nodes in this Flow.
        list_nodes_request = ListNodesInFlowRequest(flow_name=request.flow_name)
        list_nodes_result = GriptapeNodes().handle_request(list_nodes_request)
        if isinstance(list_nodes_result, ListNodesInFlowResult_Failure):
            details = f"Attempted to delete Flow '{request.flow_name}', but failed while attempting to get the list of Nodes owned by this Flow."
            print(details)  # TODO(griptape): Move to Log
            result = DeleteFlowResult_Failure()
            return result
        node_names = list_nodes_result.node_names
        for node_name in node_names:
            delete_node_request = DeleteNodeRequest(node_name=node_name)
            delete_node_result = GriptapeNodes().handle_request(delete_node_request)
            if isinstance(delete_node_result, DeleteNodeResult_Failure):
                details = f"Attempted to delete Flow '{request.flow_name}', but failed while attempting to delete child Node '{node_name}'."
                print(details)  # TODO(griptape): Move to Log
                result = DeleteFlowResult_Failure()
                return result

        # Delete all child Flows of this Flow.
        list_flows_request = ListFlowsInFlowRequest(parent_flow_name=request.flow_name)
        list_flows_result = GriptapeNodes().handle_request(list_flows_request)
        if isinstance(list_flows_result, ListFlowsInFlowResult_Failure):
            details = f"Attempted to delete Flow '{request.flow_name}', but failed while attempting to get the list of Flows owned by this Flow."
            print(details)  # TODO(griptape): Move to Log
            result = DeleteFlowResult_Failure()
            return result
        flow_names = list_flows_result.flow_names
        for flow_name in flow_names:
            # Delete them.
            delete_flow_request = DeleteFlowRequest(flow_name=flow_name)
            delete_flow_result = GriptapeNodes().handle_request(delete_flow_request)
            if isinstance(delete_flow_result, DeleteFlowResult_Failure):
                details = f"Attempted to delete Flow '{request.flow_name}', but failed while attempting to delete child Flow '{flow_name}'."
                print(details)  # TODO(griptape): Move to Log
                result = DeleteFlowResult_Failure()
                return result

        # If we've made it this far, we have deleted all the children Flows and their nodes.
        # Remove the flow from our map.
        obj_mgr.del_obj_by_name(request.flow_name)
        del self._name_to_parent_name[request.flow_name]

        details = f"Successfully deleted Flow '{request.flow_name}'."
        print(details)  # TODO(griptape): Move to Log
        result = DeleteFlowResult_Success()
        return result

    def on_get_is_flow_running_request(self, request: GetIsFlowRunningRequest) -> ResultPayload:
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(request.flow_name, ControlFlow)
        if flow is None:
            details = f"Attempted to get Flow '{request.flow_name}', but no Flow with that name could be found."
            print(details)  # TODO(griptape): Move to Log
            result = GetIsFlowRunningResult_Failure()
            return result
        try:
            is_running = flow.check_for_existing_running_flow()
        except Exception:
            details = f"Error while trying to get status of '{request.flow_name}'."
            print(details)  # TODO(griptape): Move to Log
            result = GetIsFlowRunningResult_Failure()
            return result
        return GetIsFlowRunningResult_Success(is_running=is_running)

    def on_list_nodes_in_flow_request(self, request: ListNodesInFlowRequest) -> ResultPayload:
        # Does this Flow even exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(request.flow_name, ControlFlow)
        if flow is None:
            details = (
                f"Attempted to list Nodes in Flow '{request.flow_name}', but no Flow with that name could be found."
            )
            print(details)  # TODO(griptape): Move to Log
            result = ListNodesInFlowResult_Failure()
            return result

        details = f"Successfully got the list of Nodes within Flow '{request.flow_name}'."
        print(details)  # TODO(griptape): Move to Log

        ret_list = list(flow.nodes.keys())
        result = ListNodesInFlowResult_Success(node_names=ret_list)
        return result

    def on_list_flows_in_flow_request(self, request: ListFlowsInFlowRequest) -> ResultPayload:
        if request.parent_flow_name is not None:
            # Does this Flow even exist?
            obj_mgr = GriptapeNodes().get_instance().ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(request.parent_flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to list Flows that are children of Flow '{request.parent_flow_name}', but no Flow with that name could be found."
                print(details)  # TODO(griptape): Move to Log
                result = ListFlowsInFlowResult_Failure()
                return result

        # Create a list of all child flow names that point DIRECTLY to us.
        ret_list = []
        for flow_name, parent_name in self._name_to_parent_name.items():
            if parent_name == request.parent_flow_name:
                ret_list.append(flow_name)

        details = f"Successfully got the list of Flows that are direct children of Flow '{request.parent_flow_name}'."
        print(details)  # TODO(griptape): Move to Log

        result = ListFlowsInFlowResult_Success(flow_names=ret_list)
        return result

    def get_flow_by_name(self, flow_name: str) -> ControlFlow:
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is None:
            msg = f"Flow with name {flow_name} doesn't exist"
            raise KeyError(msg)

        return flow

    def handle_flow_rename(self, old_name: str, new_name: str) -> None:
        # Replace the old flow name and its parent first.
        parent = self._name_to_parent_name[old_name]
        self._name_to_parent_name[new_name] = parent
        del self._name_to_parent_name[old_name]

        # Now iterate through everyone who pointed to the old one as a parent and update it.
        for flow_name, parent_name in self._name_to_parent_name.items():
            if parent_name == old_name:
                self._name_to_parent_name[flow_name] = new_name

        # Let the Node Manager know about the change, too.
        GriptapeNodes.NodeManager().handle_flow_rename(old_name=old_name, new_name=new_name)

    def on_create_connection_request(self, request: CreateConnectionRequest) -> ResultPayload:  # noqa: PLR0911, PLR0912, PLR0915, C901 TODO(griptape): resolve
        # Vet the two nodes first.
        source_node = None
        try:
            source_node = GriptapeNodes.NodeManager().get_node_by_name(request.source_node_name)
        except KeyError as err:
            details = f'Connection failed: "{request.source_node_name}" does not exist. Error: {err}.'
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result

        target_node = None
        try:
            target_node = GriptapeNodes.NodeManager().get_node_by_name(request.target_node_name)
        except KeyError as err:
            details = f'Connection failed: "{request.target_node_name}" does not exist. Error: {err}.'
            print(details)  # TODO(griptape): Move to Log
            result = CreateConnectionResult_Failure()
            return result

        # The two nodes exist.
        # Get the parent flows.
        source_flow_name = None
        source_flow = None
        try:
            source_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(request.source_node_name)
            source_flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name=source_flow_name)
        except KeyError as err:
            details = f'Connection "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}" failed: {err}.'
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(request.target_node_name)
            GriptapeNodes.FlowManager().get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}" failed: {err}.'
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result

        # CURRENT RESTRICTION: Now vet the parents are in the same Flow (yes this sucks)
        if target_flow_name != source_flow_name:
            details = f'Connection "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}" failed: Different flows.'
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection failed: "{request.source_node_name}.{request.source_parameter_name}" not found'
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            # TODO(griptape): We may make this a special type of failure, or attempt to handle it gracefully.
            details = f'Connection failed: "{request.target_node_name}.{request.target_parameter_name}" not found'
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result
        # Validate parameter modes accept this type of connection.
        source_modes_allowed = source_param.allowed_modes
        if ParameterMode.OUTPUT not in source_modes_allowed:
            details = f'Connection failed: "{request.source_node_name}.{request.source_parameter_name}" is not an allowed OUTPUT'
            print(details)  # TODO(griptape): Move to Log
            result = CreateConnectionResult_Failure()
            return result

        target_modes_allowed = target_param.allowed_modes
        if ParameterMode.INPUT not in target_modes_allowed:
            details = f'Connection failed: "{request.target_node_name}.{request.target_parameter_name}" is not an allowed INPUT'
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result

        # Validate that at least ONE data type from the source is allowed by the target.
        any_types_matched = False
        source_types_allowed = source_param.allowed_types
        for source_type_allowed in source_types_allowed:
            if target_param.is_type_allowed(source_type_allowed):
                any_types_matched = True
                break

        if not any_types_matched:
            details = f'Connection failed on type mismatch "{request.source_node_name}.{request.source_parameter_name}" types({source_param.allowed_types}) to "{request.target_node_name}.{request.target_parameter_name}" types({target_param.allowed_types}) '
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result

        # Ask each node involved to bless this union.
        if not source_node.allow_outgoing_connection(
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection failed : "{request.source_node_name}.{request.source_parameter_name}" rejected the connection '
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result

        if not target_node.allow_incoming_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        ):
            details = f'Connection failed : "{request.target_node_name}.{request.target_parameter_name}" rejected the connection '
            print(details)  # TODO(griptape): Move to Log

            result = CreateConnectionResult_Failure()
            return result
        try:
            # Actually create the Connection.
            source_flow.add_connection(
                source_node=source_node,
                source_parameter=source_param,
                target_node=target_node,
                target_parameter=target_param,
            )
        except ValueError as e:
            details = f'Connection failed : "{e}"'
            print(details)
            return CreateConnectionResult_Failure()

        # Let the source make any internal handling decisions now that the Connection has been made.
        source_node.handle_outgoing_connection(
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        )

        # And target.
        target_node.handle_incoming_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        )

        details = f'Connected "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}"'
        details = f'Connected "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}"'
        print(details)  # TODO(griptape): Move to Log

        # Now update the parameter values if it exists.
        # check if it's been resolved/has a value in parameter_output_values
        if source_param.name in source_node.parameter_output_values:
            value = source_node.parameter_output_values[source_param.name]
        # if it doesn't let's use the one in parameter_values! that's the most updated.
        elif source_param.name in source_node.parameter_values:
            value = source_node.get_parameter_value(source_param.name)
        # if not even that.. then does it have a default value?
        elif source_param.default_value:
            value = source_param.default_value
        else:
            value = None
        # if it existed somewhere and actually has a value - Set the parameter!
        if value:
            GriptapeNodes.handle_request(
                SetParameterValueRequest(
                    parameter_name=target_param.name,
                    node_name=target_node.name,
                    value=value,
                )
            )

        result = CreateConnectionResult_Success()

        return result

    def on_delete_connection_request(self, request: DeleteConnectionRequest) -> ResultPayload:  # noqa: PLR0911, PLR0915, C901 TODO(griptape): resolve
        # Vet the two nodes first.
        source_node = None
        try:
            source_node = GriptapeNodes.NodeManager().get_node_by_name(request.source_node_name)
        except KeyError as err:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". Error: {err}'
            print(details)  # TODO(griptape): Move to Log

            result = DeleteConnectionResult_Failure()
            return result

        target_node = None
        try:
            target_node = GriptapeNodes.NodeManager().get_node_by_name(request.target_node_name)
        except KeyError as err:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". Error: {err}'
            print(details)  # TODO(griptape): Move to Log

            result = DeleteConnectionResult_Failure()
            return result

        # The two nodes exist.
        # Get the parent flows.
        source_flow_name = None
        source_flow = None
        try:
            source_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(request.source_node_name)
            source_flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name=source_flow_name)
        except KeyError as err:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". Error: {err}'
            print(details)

            result = DeleteConnectionResult_Failure()
            return result

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(request.target_node_name)
            GriptapeNodes.FlowManager().get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". Error: {err}'
            print(details)  # TODO(griptape): Move to Log

            result = DeleteConnectionResult_Failure()
            return result

        # CURRENT RESTRICTION: Now vet the parents are in the same Flow (yes this sucks)
        if target_flow_name != source_flow_name:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". They are in different Flows (TEMPORARY RESTRICTION).'
            print(details)  # TODO(griptape): Move to Log

            result = DeleteConnectionResult_Failure()
            return result

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" Not found.'
            print(details)  # TODO(griptape): Move to Log

            result = DeleteConnectionResult_Failure()
            return result

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            details = f'Connection not deleted "{request.target_node_name}.{request.target_parameter_name}" Not found.'
            print(details)  # TODO(griptape): Move to Log

            result = DeleteConnectionResult_Failure()
            return result

        # TEMP HACK: Data connections appear to reverse Source and Target. TODO(griptape): Let's reconcile this.
        if ParameterControlType.__name__ not in source_param.allowed_types:
            temp_node = source_node
            temp_param = source_param
            source_node = target_node
            source_param = target_param
            target_node = temp_node
            target_param = temp_param

        # Vet that a Connection actually exists between them already.
        if not source_flow.has_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection does not exist: "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}"'
            print(details)  # TODO(griptape): Move to Log

            result = DeleteConnectionResult_Failure()
            return result

        # Remove the connection.
        if not source_flow.remove_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". Unknown failure.'
            print(details)  # TODO(griptape): Move to Log

            result = DeleteConnectionResult_Failure()
            return result

        details = f'Connection "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}" deleted.'
        print(details)  # TODO(griptape): Move to Log

        result = DeleteConnectionResult_Success()
        return result

    def on_start_flow_request(self, request: StartFlowRequest) -> ResultPayload:
        # which flow
        flow_name = request.flow_name
        debug_mode = request.debug_mode
        if not flow_name:
            details = "Must provide flow name to start a flow."
            print(details)  # TODO(griptape): Move to Log

            return StartFlowResult_Failure()
        # get the flow by ID
        flow = self.get_flow_by_name(flow_name)
        if not flow:
            details = f"Cannot start flow. Flow with name {flow_name} does not exist."
            print(details)  # TODO(griptape): Move to Log

            return StartFlowResult_Failure()
        # A node has been provided to either start or to run up to.
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = (
                GriptapeNodes.get_instance()
                ._object_manager
                .attempt_get_object_by_name_as_type(flow_node_name, NodeBase)
            )
            if not flow_node:
                details = f"Provided node with name {flow_node_name} does not exist"
                print(details)
                return StartFlowResult_Failure()
            # lets get the first control node in the flow!
            start_node = flow.get_start_node_from_node(flow_node)
            # if the start is not the node provided, set a breakpoint at the stop (we're running up until there)
            if not start_node:
                details = f"Start node for node with name {flow_node_name} does not exist"
                print(details)
                return StartFlowResult_Failure()
            if start_node != flow_node:
                flow_node.stop_flow = True
        else:
            # we wont hit this if we dont have a request id, our requests always have nodes
            # If there is a request, reinitialize the queue
            flow.get_start_node_queue()  # initialize the start flow queue!
            start_node = None
        try:
            flow.start_flow(start_node, debug_mode)
        except Exception as e:
            details = f"Failed to kick off flow with name {flow_name}. Exception occurred: {e} "
            print(details)  # TODO(griptape): Move to Log
            return StartFlowResult_Failure()

        details = f"Successfully kicked off flow with name {flow_name}"
        print(details)  # TODO(griptape): Move to Log

        return StartFlowResult_Success()

    def on_get_flow_state_request(self, event: GetFlowStateRequest) -> ResultPayload:
        flow_name = event.flow_name
        if not flow_name:
            details = "Could not get flow state. No flow name was provided."
            print(details)
            return GetFlowStateResult_Failure()
        flow = self.get_flow_by_name(flow_name)
        if not flow:
            details = f"Could not get flow state. No flow with name {flow_name} exists."
            print(details)
            return GetFlowStateResult_Failure()
        try:
            control_node, resolving_node = flow.flow_state()
        except Exception as e:
            details = f"Failed to get flow state of flow with name {flow_name}. Exception occurred: {e} "
            print(details)
            return GetFlowStateResult_Failure()
        details = f"Successfully got flow state for flow with name {flow_name}."
        return GetFlowStateResult_Success(control_node=control_node, resolving_node=resolving_node)

    def on_cancel_flow_request(self, request: CancelFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not cancel flow execution. No flow name was provided."
            print(details)  # TODO(griptape): Move to Log

            return CancelFlowResult_Failure()
        flow = self.get_flow_by_name(flow_name)
        if not flow:
            details = f"Could not cancel flow execution. No flow with name {flow_name} exists."
            print(details)  # TODO(griptape): Move to Log

            return CancelFlowResult_Failure()
        try:
            flow.cancel_flow_run()
        except Exception as e:
            details = f"Could not cancel flow execution. Exception: {e}"
            print(details)  # TODO(griptape): Move to Log

            return CancelFlowResult_Failure()
        details = f"Successfully cancelled flow execution with name {flow_name}"
        print(details)  # TODO(griptape): Move to Log

        return CancelFlowResult_Success()

    def on_single_node_step_request(self, request: SingleNodeStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not step flow. No flow name was provided."
            print(details)  # TODO(griptape): Move to Log

            return SingleNodeStepResult_Failure()
        flow = self.get_flow_by_name(flow_name)
        if not flow:
            details = f"Could not step flow. No flow with name {flow_name} exists."
            print(details)  # TODO(griptape): Move to Log

            return SingleNodeStepResult_Failure()
        try:
            flow.single_node_step()
        except Exception as e:
            details = f"Could not step flow. Exception: {e}"
            print(details)  # TODO(griptape): Move to Log

            return SingleNodeStepResult_Failure()

        # All completed happily
        details = f"Successfully stepped flow with name {flow_name}"
        print(details)  # TODO(griptape): Move to Log

        return SingleNodeStepResult_Success()

    def on_single_execution_step_request(self, request: SingleExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not single step flow. No flow name was provided."
            print(details)  # TODO(griptape): Move to Log

            return SingleExecutionStepResult_Failure()
        flow = self.get_flow_by_name(flow_name)
        if not flow:
            details = f"Could not single step flow. No flow with name {flow_name} exists."
            print(details)  # TODO(griptape): Move to Log

            return SingleExecutionStepResult_Failure()
        try:
            flow.single_execution_step()
        except Exception as e:
            details = f"Could not step flow. Exception: {e}"
            print(details)  # TODO(griptape): Move to Log

            return SingleNodeStepResult_Failure()
        details = f"Successfully granularly stepped flow with name {flow_name}"
        print(details)  # TODO(griptape): Move to Log

        return SingleExecutionStepResult_Success()

    def on_continue_execution_step_request(self, request: ContinueExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to continue execution step because no flow name was provided"
            print(details)  # TODO(griptape): Move to Log

            return ContinueExecutionStepResult_Failure()
        flow = self.get_flow_by_name(flow_name)
        if not flow:
            details = f"Failed to continue execution step. Flow with name {flow_name} does not exist."
            print(details)  # TODO(griptape): Move to Log

            return ContinueExecutionStepResult_Failure()
        try:
            flow.continue_executing()
        except Exception as e:
            details = f"Failed to continue execution step. An exception occurred: {e}."
            print(details)  # TODO(griptape): Move to Log
            return ContinueExecutionStepResult_Failure()
        details = f"Successfully continued flow with name {flow_name}"
        print(details)  # TODO(griptape): Move to Log
        return ContinueExecutionStepResult_Success()

    def on_unresolve_flow_request(self, request: UnresolveFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to unresolve flow because no flow name was provided"
            print(details)  # TODO(griptape): Move to Log
            return UnresolveFlowResult_Failure()
        flow = self.get_flow_by_name(flow_name)
        if not flow:
            details = f"Failed to unresolve flow because flow with name {flow_name} does not exist."
            print(details)  # TODO(griptape): Move to Log
            return UnresolveFlowResult_Failure()
        try:
            flow.unresolve_whole_flow()
        except Exception as e:
            details = f"Failed to unresolve flow. An exception occurred: {e}."
            print(details)  # TODO(griptape): Move to Log
            return UnresolveFlowResult_Failure()
        details = f"Unresolved flow with name {flow_name}"
        print(details)  # TODO(griptape): Move to Log
        return UnresolveFlowResult_Success()

    def on_app_execution_event(self, event: AppExecutionEvent) -> None:
        # Handle all events from the execution engine
        # TODO(kate): Should this somehow be modified to be specific events for the gui?
        GriptapeNodes.handle_request(event.request)

    def on_validate_flow_dependencies_request(self, request:ValidateFlowDependenciesRequest) -> ResultPayload:
        flow_name = request.flow_name
        # get the flow name
        flow = self.get_flow_by_name(flow_name)
        if not flow:
            details = f"Failed to validate flow because flow with name {flow_name} does not exist."
            print(details)  # TODO(griptape): Move to Log
            return ValidateFlowDependenciesResult_Failure()
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = GriptapeNodes.get_instance()._object_manager.attempt_get_object_by_name_as_type(flow_node_name,NodeBase)
            if not flow_node:
                details=f"Provided node with name {flow_node_name} does not exist"
                print(details)
                return ValidateFlowDependenciesResult_Failure()
            # Gets all nodes in that connected group to be ran
            nodes = flow.get_all_connected_nodes(flow_node)
        else:
            nodes = flow.nodes.values()
        # If we're just running the whole flow
        all_exceptions = []
        for node in nodes:
            exceptions = node.validate_node()
            if exceptions:
                all_exceptions = all_exceptions + exceptions
        if all_exceptions:
            return ValidateFlowDependenciesResult_Success(validation_succeeded=False, exceptions=all_exceptions)
        return ValidateFlowDependenciesResult_Success(validation_succeeded=True)

class NodeManager:
    _name_to_parent_flow_name: dict[str, str]

    def __init__(self, event_manager: EventManager) -> None:
        self._name_to_parent_flow_name = {}

        event_manager.assign_manager_to_request_type(CreateNodeRequest, self.on_create_node_request)
        event_manager.assign_manager_to_request_type(DeleteNodeRequest, self.on_delete_node_request)
        event_manager.assign_manager_to_request_type(
            GetNodeResolutionStateRequest, self.on_get_node_resolution_state_request
        )
        event_manager.assign_manager_to_request_type(GetNodeMetadataRequest, self.on_get_node_metadata_request)
        event_manager.assign_manager_to_request_type(SetNodeMetadataRequest, self.on_set_node_metadata_request)
        event_manager.assign_manager_to_request_type(
            ListConnectionsForNodeRequest, self.on_list_connections_for_node_request
        )
        event_manager.assign_manager_to_request_type(
            ListParametersOnNodeRequest, self.on_list_parameters_on_node_request
        )
        event_manager.assign_manager_to_request_type(AddParameterToNodeRequest, self.on_add_parameter_to_node_request)
        event_manager.assign_manager_to_request_type(
            RemoveParameterFromNodeRequest, self.on_remove_parameter_from_node_request
        )
        event_manager.assign_manager_to_request_type(GetParameterDetailsRequest, self.on_get_parameter_details_request)
        event_manager.assign_manager_to_request_type(
            AlterParameterDetailsRequest, self.on_alter_parameter_details_request
        )
        event_manager.assign_manager_to_request_type(GetParameterValueRequest, self.on_get_parameter_value_request)
        event_manager.assign_manager_to_request_type(SetParameterValueRequest, self.on_set_parameter_value_request)
        event_manager.assign_manager_to_request_type(ResolveNodeRequest, self.on_resolve_from_node_request)
        event_manager.assign_manager_to_request_type(GetAllNodeInfoRequest, self.on_get_all_node_info_request)
        event_manager.assign_manager_to_request_type(ValidateNodeDependenciesRequest, self.on_validate_node_dependencies_request)

    def handle_node_rename(self, old_name: str, new_name: str) -> None:
        # Replace the old node name and its parent.
        parent = self._name_to_parent_flow_name[old_name]
        self._name_to_parent_flow_name[new_name] = parent
        del self._name_to_parent_flow_name[old_name]

    def handle_flow_rename(self, old_name: str, new_name: str) -> None:
        # Find all instances where a node had the old parent and update it to the new one.
        for node_name, parent_flow_name in self._name_to_parent_flow_name.items():
            if parent_flow_name == old_name:
                self._name_to_parent_flow_name[node_name] = new_name

    def on_create_node_request(self, request: CreateNodeRequest) -> ResultPayload:
        # Validate as much as possible before we actually create one.
        parent_flow_name = request.override_parent_flow_name
        if parent_flow_name is None:
            details = f"Could not create Node of type '{request.node_type}'. No value for parent flow was supplied. This will one day come from the Current Context but we are poor and broken people. Please try your call again later."
            print(details)  # TODO(griptape): Move to Log

            result = CreateNodeResult_Failure()
            return result
        # Does this flow actually exist?
        flow_mgr = GriptapeNodes.FlowManager()
        flow = flow_mgr.get_flow_by_name(parent_flow_name)
        if flow is None:
            details = f"Could not create Node of type '{request.node_type}'. The parent Flow '{parent_flow_name}' could not be found."
            print(details)  # TODO(griptape): Move to Log

            result = CreateNodeResult_Failure()
            return result

        # Now ensure that we're giving a valid name.
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()
        final_node_name = obj_mgr.generate_name_for_object(
            type_name=request.node_type, requested_name=request.node_name
        )
        remapped_requested_node_name = (request.node_name is not None) and (request.node_name != final_node_name)

        # OK, let's try and create the Node.
        node = None
        try:
            node = LibraryRegistry.create_node(
                name=final_node_name,
                node_type=request.node_type,
                specific_library_name=request.specific_library_name,
                metadata=request.metadata,
            )
        except KeyError as err:
            details = f"Could not create Node '{final_node_name}' of type '{request.node_type}': {err}"
            print(details)  # TODO(griptape): Move to Log

            result = CreateNodeResult_Failure()
            return result

        # Add it to the Flow.
        flow.add_node(node)

        # Record keeping.
        obj_mgr.add_object_by_name(node.name, node)
        self._name_to_parent_flow_name[node.name] = parent_flow_name

        # Phew.
        details = f"Successfully created Node '{final_node_name}' of type '{request.node_type}'."

        if remapped_requested_node_name:
            details = f"{details} WARNING: Had to rename from original node name requested '{request.node_name}' as an object with this name already existed."

        print(details)  # TODO(griptape): Move to Log

        result = CreateNodeResult_Success(
            node_name=node.name,
        )
        return result

    def on_delete_node_request(self, request: DeleteNodeRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to delete a Node '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = DeleteNodeResult_Failure()
            return result

        parent_flow_name = self._name_to_parent_flow_name[request.node_name]
        parent_flow = GriptapeNodes().FlowManager().get_flow_by_name(parent_flow_name)

        # Remove all connections from this Node.
        list_node_connections_request = ListConnectionsForNodeRequest(node_name=request.node_name)
        list_connections_result = GriptapeNodes().handle_request(request=list_node_connections_request)
        if isinstance(list_connections_result, ResultPayload_Failure):
            details = f"Attempted to delete a Node '{request.node_name}'. Failed because it could not gather Connections to the Node."
            print(details)  # TODO(griptape): Move to Log

            result = DeleteNodeResult_Failure()
            return result
        # Destroy all the incoming Connections
        for incoming_connection in list_connections_result.incoming_connections:
            delete_request = DeleteConnectionRequest(
                source_node_name=incoming_connection.source_node_name,
                source_parameter_name=incoming_connection.source_parameter_name,
                target_node_name=request.node_name,
                target_parameter_name=incoming_connection.target_parameter_name,
            )
            delete_result = GriptapeNodes.handle_request(delete_request)
            if isinstance(delete_result, ResultPayload_Failure):
                details = (
                    f"Attempted to delete a Node '{request.node_name}'. Failed when attempting to delete Connection."
                )
                print(details)  # TODO(griptape): Move to Log

                result = DeleteNodeResult_Failure()
                return result

        # Destroy all the outgoing Connections
        for outgoing_connection in list_connections_result.outgoing_connections:
            delete_request = DeleteConnectionRequest(
                source_node_name=request.node_name,
                source_parameter_name=outgoing_connection.source_parameter_name,
                target_node_name=outgoing_connection.target_node_name,
                target_parameter_name=outgoing_connection.target_parameter_name,
            )
            delete_result = GriptapeNodes.handle_request(delete_request)
            if isinstance(delete_result, ResultPayload_Failure):
                details = (
                    f"Attempted to delete a Node '{request.node_name}'. Failed when attempting to delete Connection."
                )
                print(details)  # TODO(griptape): Move to Log

                result = DeleteNodeResult_Failure()
                return result

        # Remove from the owning Flow
        parent_flow.remove_node(node.name)

        # Now remove the record keeping
        obj_mgr.del_obj_by_name(request.node_name)
        del self._name_to_parent_flow_name[request.node_name]

        details = f"Successfully deleted Node '{request.node_name}'."
        print(details)  # TODO(griptape): Move to Log

        result = DeleteNodeResult_Success()
        return result

    def on_get_node_resolution_state_request(self, event: GetNodeResolutionStateRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(event.node_name, NodeBase)
        if node is None:
            details = f"Attempted to get resolution state for a Node '{event.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log
            result = GetNodeResolutionStateResult_Failure()
            return result

        node_state = node.state

        details = f"Successfully got resolution state for Node '{event.node_name}'."
        print(details)  # TODO(griptape): Move to Log

        result = GetNodeResolutionStateResult_Success(
            state=node_state.name,
        )
        return result

    def on_get_node_metadata_request(self, request: GetNodeMetadataRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to get metadata for a Node '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = GetNodeMetadataResult_Failure()
            return result

        metadata = node.metadata
        details = f"Successfully retrieved metadata for a Node '{request.node_name}'."
        print(details)  # TODO(griptape): Move to Log

        result = GetNodeMetadataResult_Success(
            metadata=metadata,
        )
        return result

    def on_set_node_metadata_request(self, request: SetNodeMetadataRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to set metadata for a Node '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = SetNodeMetadataResult_Failure()
            return result

        node.metadata = request.metadata
        details = f"Successfully set metadata for a Node '{request.node_name}'."
        print(details)  # TODO(griptape): Move to Log

        result = SetNodeMetadataResult_Success()
        return result

    def on_list_connections_for_node_request(self, request: ListConnectionsForNodeRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to list Connections for a Node '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = ListConnectionsForNodeResult_Failure()
            return result

        parent_flow_name = self._name_to_parent_flow_name[request.node_name]
        parent_flow = GriptapeNodes().FlowManager().get_flow_by_name(parent_flow_name)

        # Kinda gross, but let's do it
        connection_mgr = parent_flow.connections
        # get outgoing connections
        outgoing_connections_list = []
        if request.node_name in connection_mgr.outgoing_index:
            outgoing_connections_list = [
                OutgoingConnection(
                    source_parameter_name=connection.source_parameter.name,
                    target_node_name=connection.target_node.name,
                    target_parameter_name=connection.target_parameter.name,
                )
                for connection_lists in connection_mgr.outgoing_index[request.node_name].values()
                for connection_id in connection_lists
                for connection in [connection_mgr.connections[connection_id]]
            ]
        # get incoming connections
        incoming_connections_list = []
        if request.node_name in connection_mgr.incoming_index:
            incoming_connections_list = [
                IncomingConnection(
                    source_node_name=connection.source_node.name,
                    source_parameter_name=connection.source_parameter.name,
                    target_parameter_name=connection.target_parameter.name,
                )
                for connection_lists in connection_mgr.incoming_index[request.node_name].values()
                for connection_id in connection_lists
                for connection in [
                    connection_mgr.connections[connection_id]
                ]  # This creates a temporary one-item list with the connection
            ]

        details = f"Successfully listed all Connections to and from Node '{node.name}'."
        print(details)  # TODO(griptape): Move to Log

        result = ListConnectionsForNodeResult_Success(
            incoming_connections=incoming_connections_list,
            outgoing_connections=outgoing_connections_list,
        )
        return result

    def on_list_parameters_on_node_request(self, request: ListParametersOnNodeRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to list Parameters for a Node '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = ListParametersOnNodeResult_Failure()
            return result

        ret_list = [param.name for param in node.parameters]

        details = f"Params on {node.name} = {ret_list}"
        print(details)  # TODO(griptape): Move to Log

        result = ListParametersOnNodeResult_Success(
            parameter_names=ret_list,
        )
        return result

    def on_add_parameter_to_node_request(self, request: AddParameterToNodeRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to add Parameter '{request.parameter_name}' to a Node '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = AddParameterToNodeResult_Failure()
            return result

        # Does the Node already have a parameter by this name?
        if node.get_parameter_by_name(request.parameter_name) is not None:
            details = f"Attempted to add Parameter '{request.parameter_name}' to Node '{request.node_name}'. Failed because it already had a Parameter with that name on it. Parameter names must be unique within the Node."
            print(details)  # TODO(griptape): Move to Log

            result = AddParameterToNodeResult_Failure()
            return result

        # Let's see if the Parameter is properly formed.
        # If a Parameter is intended for Control, it needs to have that be the exclusive type.
        if ParameterControlType.__name__ in request.allowed_types and len(request.allowed_types) != 1:
            details = f"Attempted to add Parameter '{request.parameter_name}' to Node '{request.node_name}'. Failed because it had 'ParameterControlType' with other types allowed. If a Parameter is intended for control, it must only accept that type."
            print(details)  # TODO(griptape): Move to Log

            result = AddParameterToNodeResult_Failure()
            return result
        # Make sure list of types are correct.
        invalid_type_list = [
            allowed_type for allowed_type in request.allowed_types if not TypeValidator.validate_type_spec(allowed_type)
        ]

        if len(invalid_type_list) > 0:
            details = f"Attempted to add Parameter '{request.parameter_name}' but the following allowed types were not valid: {invalid_type_list!s}."
            print(details)  # TODO(griptape): Move to Log

            result = AddParameterToNodeResult_Failure()
            return result

        allowed_modes = set()
        if request.mode_allowed_input:
            allowed_modes.add(ParameterMode.INPUT)
        if request.mode_allowed_property:
            allowed_modes.add(ParameterMode.PROPERTY)
        if request.mode_allowed_output:
            allowed_modes.add(ParameterMode.OUTPUT)

        # Let's roll, I guess.
        new_param = Parameter(
            name=request.parameter_name,
            allowed_types=request.allowed_types,
            default_value=request.default_value,
            user_defined=True,
            tooltip=request.tooltip,
            tooltip_as_input=request.tooltip_as_input,
            tooltip_as_property=request.tooltip_as_property,
            tooltip_as_output=request.tooltip_as_output,
            allowed_modes=allowed_modes,
            ui_options=request.ui_options,
        )
        try:
            node.add_parameter(new_param)
        except Exception as e:
            details = f"Couldn't add parameter with name {request.parameter_name} to node. Error: {e}"
            print(details)
            return AddParameterToNodeResult_Failure()

        details = f"Successfully added Parameter '{request.parameter_name}' to Node '{request.node_name}'."
        print(details)  # TODO(griptape): Move to Log

        result = AddParameterToNodeResult_Success()
        return result

    def on_remove_parameter_from_node_request(self, request: RemoveParameterFromNodeRequest) -> ResultPayload:  # noqa: C901
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from a Node '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = RemoveParameterFromNodeResult_Failure()
            return result

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(request.parameter_name)
        if parameter is None:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because it didn't have a Parameter with that name on it."
            print(details)  # TODO(griptape): Move to Log

            result = RemoveParameterFromNodeResult_Failure()
            return result

        # No tricky stuff, users!
        if parameter.user_defined is False:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because the Parameter was not user-defined (i.e., critical to the Node implementation). Only user-defined Parameters can be removed from a Node."
            print(details)  # TODO(griptape): Move to Log

            result = RemoveParameterFromNodeResult_Failure()
            return result

        # Get all the connections to/from this Parameter.
        list_node_connections_request = ListConnectionsForNodeRequest(node_name=request.node_name)
        list_connections_result = GriptapeNodes().handle_request(request=list_node_connections_request)
        if isinstance(list_connections_result, ListConnectionsForNodeResult_Failure):
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because we were unable to get a list of Connections for the Parameter's Node."
            print(details)  # TODO(griptape): Move to Log

            result = RemoveParameterFromNodeResult_Failure()
            return result

        # We have a list of all connections to the NODE. Sift down to just those that are about this PARAMETER.

        # Destroy all the incoming Connections to this PARAMETER
        for incoming_connection in list_connections_result.incoming_connections:
            if incoming_connection.target_parameter_name == request.parameter_name:
                delete_request = DeleteConnectionRequest(
                    source_node_name=incoming_connection.source_node_name,
                    source_parameter_name=incoming_connection.source_parameter_name,
                    target_node_name=request.node_name,
                    target_parameter_name=incoming_connection.target_parameter_name,
                )
                delete_result = GriptapeNodes.handle_request(delete_request)
                if isinstance(delete_result, DeleteConnectionResult_Failure):
                    details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because we were unable to delete a Connection for that Parameter."
                    print(details)  # Move to Log

                    result = RemoveParameterFromNodeResult_Failure()

        # Destroy all the outgoing Connections from this PARAMETER
        for outgoing_connection in list_connections_result.outgoing_connections:
            if outgoing_connection.source_parameter_name == request.parameter_name:
                delete_request = DeleteConnectionRequest(
                    source_node_name=request.node_name,
                    source_parameter_name=outgoing_connection.source_parameter_name,
                    target_node_name=outgoing_connection.target_node_name,
                    target_parameter_name=outgoing_connection.target_parameter_name,
                )
                delete_result = GriptapeNodes.handle_request(delete_request)
                if isinstance(delete_result, DeleteConnectionResult_Failure):
                    details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because we were unable to delete a Connection for that Parameter."
                    print(details)  # TODO(griptape): Move to Log

                    result = RemoveParameterFromNodeResult_Failure()

        # Delete the Parameter itself.
        node.remove_parameter(parameter)

        details = f"Successfully removed Parameter '{request.parameter_name}' from Node '{request.node_name}'."
        print(details)  # TODO(griptape): Move to Log

        result = RemoveParameterFromNodeResult_Success()
        return result

    def on_get_parameter_details_request(self, request: GetParameterDetailsRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to get details for Parameter '{request.parameter_name}' from a Node '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = GetParameterDetailsResult_Failure()
            return result

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(request.parameter_name)
        if parameter is None:
            details = f"Attempted to get details for Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because it didn't have a Parameter with that name on it."
            print(details)  # TODO(griptape): Move to Log

            result = GetParameterDetailsResult_Failure()
            return result

        # Let's bundle up the details.
        modes_allowed = parameter.allowed_modes
        allows_input = ParameterMode.INPUT in modes_allowed
        allows_property = ParameterMode.PROPERTY in modes_allowed
        allows_output = ParameterMode.OUTPUT in modes_allowed

        details = f"Successfully got details for Parameter '{request.parameter_name}' from Node '{request.node_name}'."
        print(details)  # TODO(griptape): Move to Log

        result = GetParameterDetailsResult_Success(
            allowed_types=parameter.allowed_types,
            default_value=parameter.default_value,
            tooltip=parameter.tooltip,
            tooltip_as_input=parameter.tooltip_as_input,
            tooltip_as_property=parameter.tooltip_as_property,
            tooltip_as_output=parameter.tooltip_as_output,
            mode_allowed_input=allows_input,
            mode_allowed_property=allows_property,
            mode_allowed_output=allows_output,
            is_user_defined=parameter.user_defined,
            ui_options=parameter.ui_options,
        )
        return result

    def on_alter_parameter_details_request(self, request: AlterParameterDetailsRequest) -> ResultPayload:  # noqa: C901, PLR0912, PLR0915
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to alter details for Parameter '{request.parameter_name}' from Node '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = AlterParameterDetailsResult_Failure()
            return result

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(request.parameter_name)
        if parameter is None:
            details = f"Attempted to alter details for Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because it didn't have a Parameter with that name on it."
            print(details)  # TODO(griptape): Move to Log

            result = AlterParameterDetailsResult_Failure()
            return result

        # No tricky stuff, users!
        if parameter.user_defined is False and request.request_id:
            # TODO(griptape): there may be SOME properties on a non-user-defined Parameter that can be changed
            details = f"Attempted to alter details for Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because the Parameter was not user-defined (i.e., critical to the Node implementation). Only user-defined Parameters can be removed from a Node."
            print(details)  # TODO(griptape): Move to Log

            result = AlterParameterDetailsResult_Failure()
            return result

        # TODO(griptape): Verify that we can get through all the OTHER tricky stuff before we proceed to actually making changes.
        # Now change all the values on the Parameter.
        if request.allowed_types is not None:
            # Convert from string to list of types.
            invalid_type_list = [
                allowed_type
                for allowed_type in request.allowed_types
                if not TypeValidator.validate_type_spec(allowed_type)
            ]

            if len(invalid_type_list) > 0:
                details = f"Attempted to alter Parameter '{request.parameter_name}' but the following allowed types were not valid: {invalid_type_list!s}."
                print(details)  # TODO(griptape): Move to Log

                result = AddParameterToNodeResult_Failure()
                return result
            # TODO(griptape): reconcile current value with types allowed
            parameter.allowed_types = request.allowed_types
        if request.default_value is not None:
            # TODO(griptape): vet that default value matches types allowed
            node.parameter_values[request.parameter_name] = request.default_value
        if request.mode_allowed_input is not None:
            # TODO(griptape): may alter existing connections
            if request.mode_allowed_input is True:
                parameter.allowed_modes.add(ParameterMode.INPUT)
            else:
                parameter.allowed_modes.discard(ParameterMode.INPUT)
        if request.mode_allowed_property is not None:
            # TODO(griptape): may alter existing connections
            if request.mode_allowed_property is True:
                parameter.allowed_modes.add(ParameterMode.PROPERTY)
            else:
                parameter.allowed_modes.discard(ParameterMode.PROPERTY)
        if request.mode_allowed_output is not None:
            # TODO(griptape): may alter existing connections
            if request.mode_allowed_output is True:
                parameter.allowed_modes.add(ParameterMode.OUTPUT)
            else:
                parameter.allowed_modes.discard(ParameterMode.OUTPUT)
        if request.tooltip is not None:
            parameter.tooltip = request.tooltip
        if request.tooltip_as_input is not None:
            parameter.tooltip_as_input = request.tooltip_as_input
        if request.tooltip_as_property is not None:
            parameter.tooltip_as_property = request.tooltip_as_property
        if request.tooltip_as_output is not None:
            parameter.tooltip_as_output = request.tooltip_as_output
        if request.ui_options is not None:
            parameter.ui_options = request.ui_options

        details = (
            f"Successfully altered details for Parameter '{request.parameter_name}' from Node '{request.node_name}'."
        )
        print(details)  # TODO(griptape): Move to Log

        result = AlterParameterDetailsResult_Success()
        return result

    def on_get_parameter_value_request(self, request: GetParameterValueRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        # Parse the parameter name to check for list indexing
        param_name = request.parameter_name

        # Get the node
        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f'"{request.node_name}" not found'
            print(details)  # TODO(griptape): Move to Log
            return GetParameterValueResult_Failure()

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(param_name)
        if parameter is None:
            details = f'"{request.node_name}.{param_name}" not found'
            print(details)  # TODO(griptape): Move to Log
            return GetParameterValueResult_Failure()

        # Values are actually stored on the NODE, so let's ask them.
        if param_name not in node.parameter_values:
            # Check if it might be in output values (for output parameters)
            if param_name in node.parameter_output_values:
                data_value = node.parameter_output_values[param_name]
            else:
                # Use the default if not found in either place
                data_value = parameter.default_value
        else:
            data_value = node.parameter_values[param_name]

        # Definitely a better way to do this.
        data_value_type = type(data_value)
        data_value_type_str = None
        for allowed_type_str in parameter.allowed_types:
            allowed_type = TypeValidator.convert_to_type(allowed_type_str)
            if allowed_type == data_value_type:
                data_value_type_str = allowed_type_str
                break

        # TODO(griptape): Handle for dict type

        if not data_value_type_str and isinstance(data_value, dict) and "type" in data_value:
            data_value_type_str = data_value["type"]
            if "image" in data_value_type_str:
                data_value_type_str = "ImageArtifact"

        if data_value_type_str is None:
            data_value_type_str = str(data_value_type)
            print(
                f"WARNING: Could not find data value type '{data_value_type_str}' in the list of data types allowed by Parameter '{param_name}'; letting Python do the conversion."
            )
        # Cool.
        details = f"{request.node_name}.{request.parameter_name} = {data_value}"
        print(details)  # TODO(griptape): Move to Log

        result = GetParameterValueResult_Success(
            data_type=data_value_type_str,
            value=TypeValidator.safe_serialize(data_value),
        )
        return result

    # added ignoring C901 since this method is overly long because of granular error checking, not actual complexity.
    def on_set_parameter_value_request(self, request: SetParameterValueRequest) -> ResultPayload:  # noqa: PLR0911 C901 TODO(griptape): resolve
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        # Parse the parameter name to check for list indexing
        param_name = request.parameter_name

        # Get the node
        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f'"{request.node_name}" not found'
            print(details)  # TODO(griptape): Move to Log
            return SetParameterValueResult_Failure()

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(param_name)
        if parameter is None:
            details = f'"{request.node_name}.{param_name}" not found'
            print(details)  # TODO(griptape): Move to Log

            result = SetParameterValueResult_Failure()
            return result

        # Validate that parameters can be set at all
        if not parameter.settable:
            details = f'"{request.node_name}.{request.parameter_name}" is not settable'
            print(details)  # TODO(griptape): Move to Log
            result = SetParameterValueResult_Failure()
            return result

        object_created = request.value
        # here we need to see if type_of matches the actual value.
        # Is this value kosher for the types allowed?
        if not parameter.is_value_allowed(object_created) and not (
            isinstance(object_created, dict) and "type" in object_created
        ):
            details = f'set_value for "{request.node_name}.{request.parameter_name}" failed.  type "{object_created.__class__.__name__}" not in allowed types:{parameter.allowed_types}'
            print(details)  # TODO(griptape): Move to Log

            result = SetParameterValueResult_Failure()
            return result

        try:
            parent_flow_name = self.get_node_parent_flow_by_name(node.name)
        except KeyError:
            details = f'set_value for "{request.node_name}.{request.parameter_name}" failed. Parent flow does not exist. Could not unresolve future nodes.'
            print(details)
            return SetParameterValueResult_Failure()
        parent_flow = obj_mgr.attempt_get_object_by_name_as_type(parent_flow_name, ControlFlow)
        if not parent_flow:
            details = f'set_value for "{request.node_name}.{request.parameter_name}" failed. Parent flow does not exist. Could not unresolve future nodes.'
            print(details)
            return SetParameterValueResult_Failure()
        try:
            parent_flow.connections.unresolve_future_nodes(node)
        except Exception as e:
            details = f'set_value for "{request.node_name}.{request.parameter_name}" failed. Exception: {e}'
            print(details)
            return SetParameterValueResult_Failure()

        # Values are actually stored on the NODE.
        modified_parameters = node.set_parameter_value(request.parameter_name, object_created)
        if modified_parameters:
            for modified_parameter_name in modified_parameters:
                modified_request = GetParameterDetailsRequest(modified_parameter_name, node.name)
                GriptapeNodes.handle_request(modified_request)
        # Mark node as unresolved
        node.state = NodeResolutionState.UNRESOLVED
        # Get the flow
        # Pass the value through!
        conn_output_nodes = parent_flow.get_connected_output_parameters(node, parameter)
        for target_node, target_parameter in conn_output_nodes:
            GriptapeNodes.get_instance().handle_request(
                SetParameterValueRequest(
                    parameter_name=target_parameter.name,
                    node_name=target_node.name,
                    value=object_created,
                )
            )

        # Cool.
        details = f'"{request.node_name}.{request.parameter_name}" = {object_created}'
        print(details)  # TODO(griptape): Move to Log

        result = SetParameterValueResult_Success()
        return result

    # For C901 (too complex): Need to give customers explicit reasons for failure on each case.
    # For PLR0911 (too many return statements): don't want to do a ton of nested chains of success,
    # want to give clear reasoning for each failure.
    # For PLR0915 (too many statements): very little reusable code here, want to be explicit and
    # make debugger use friendly.
    def on_get_all_node_info_request(self, request: GetAllNodeInfoRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0915
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, NodeBase)
        if node is None:
            details = f"Attempted to get all info for Node named '{request.node_name}', but no such Node was found."
            print(details)  # TODO(griptape): Move to Log

            result = GetAllNodeInfoResult_Failure()
            return result

        get_metadata_request = GetNodeMetadataRequest(node_name=request.node_name)
        get_metadata_result = GriptapeNodes.NodeManager().on_get_node_metadata_request(get_metadata_request)
        if not get_metadata_result.succeeded():
            details = (
                f"Attempted to get all info for Node named '{request.node_name}', but failed getting the metadata."
            )
            print(details)  # TODO(griptape): Move to Log

            result = GetAllNodeInfoResult_Failure()
            return result

        get_resolution_state_request = GetNodeResolutionStateRequest(node_name=request.node_name)
        get_resolution_state_result = GriptapeNodes.NodeManager().on_get_node_resolution_state_request(
            get_resolution_state_request
        )
        if not get_resolution_state_result.succeeded():
            details = f"Attempted to get all info for Node named '{request.node_name}', but failed getting the resolution state."
            print(details)  # TODO(griptape): Move to Log

            result = GetAllNodeInfoResult_Failure()
            return result

        list_connections_request = ListConnectionsForNodeRequest(node_name=request.node_name)
        list_connections_result = GriptapeNodes.NodeManager().on_list_connections_for_node_request(
            list_connections_request
        )
        if not list_connections_result.succeeded():
            details = f"Attempted to get all info for Node named '{request.node_name}', but failed listing all connections for it."
            print(details)  # TODO(griptape): Move to Log

            result = GetAllNodeInfoResult_Failure()
            return result

        list_parameters_request = ListParametersOnNodeRequest(node_name=request.node_name)
        list_parameters_result = GriptapeNodes.NodeManager().on_list_parameters_on_node_request(list_parameters_request)
        if not list_parameters_result.succeeded():
            details = f"Attempted to get all info for Node named '{request.node_name}', but failed listing all Parameters on it."
            print(details)  # TODO(griptape): Move to Log

            result = GetAllNodeInfoResult_Failure()
            return result

        # Cast everything to get the linter off our back.
        try:
            get_metadata_success = cast("GetNodeMetadataResult_Success", get_metadata_result)
            get_resolution_state_success = cast("GetNodeResolutionStateResult_Success", get_resolution_state_result)
            list_connections_success = cast("ListConnectionsForNodeResult_Success", list_connections_result)
            list_parameters_success = cast("ListParametersOnNodeResult_Success", list_parameters_result)
        except Exception as err:
            details = f"Attempted to get all info for Node named '{request.node_name}'. Failed due to error: {err}."
            print(details)  # TODO(griptape): Move to Log

            result = GetAllNodeInfoResult_Failure()
            return result

        # Now go through all the Parameters.
        parameter_name_to_info = {}

        for param_name in list_parameters_success.parameter_names:
            # Parameter details up first.
            get_parameter_details_request = GetParameterDetailsRequest(
                parameter_name=param_name, node_name=request.node_name
            )
            get_parameter_details_result = GriptapeNodes.NodeManager().on_get_parameter_details_request(
                get_parameter_details_request
            )

            if not get_parameter_details_result.succeeded():
                details = f"Attempted to get all info for Node named '{request.node_name}', but failed getting details for Parameter '{param_name}'."
                print(details)  # TODO(griptape): Move to Log

                result = GetAllNodeInfoResult_Failure()
                return result

            # Now the...gulp...value.
            get_parameter_value_request = GetParameterValueRequest(
                parameter_name=param_name, node_name=request.node_name
            )
            get_parameter_value_result = GriptapeNodes.NodeManager().on_get_parameter_value_request(
                get_parameter_value_request
            )

            if not get_parameter_value_result.succeeded():
                details = f"Attempted to get all info for Node named '{request.node_name}', but failed getting value for Parameter '{param_name}'."
                print(details)  # TODO(griptape): Move to Log

                result = GetAllNodeInfoResult_Failure()
                return result

            # They may have succeeded, but are they OUR type of succeeded?
            try:
                get_parameter_details_success = cast("GetParameterDetailsResult_Success", get_parameter_details_result)
                get_parameter_value_success = cast("GetParameterValueResult_Success", get_parameter_value_result)
            except Exception as err:
                details = f"Attempted to get all info for Node named '{request.node_name}'. Failed due to error: {err}."
                print(details)  # TODO(griptape): Move to Log

                result = GetAllNodeInfoResult_Failure()
                return result

            # OK, add it to the parameter dictionary.
            parameter_name_to_info[param_name] = ParameterInfoValue(
                details=get_parameter_details_success, value=get_parameter_value_success
            )

        details = f"Successfully got all node info for node '{request.node_name}'."
        print(details)  # TODO(griptape): Move to Log
        result = GetAllNodeInfoResult_Success(
            metadata=get_metadata_success.metadata,
            node_resolution_state=get_resolution_state_success.state,
            connections=list_connections_success,
            parameter_name_to_info=parameter_name_to_info,
        )
        return result

    def get_node_by_name(self, name: str) -> NodeBase:
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(name, NodeBase)
        if node is None:
            msg = f"Node '{name}' not found."
            raise ValueError(msg)

        return node

    def get_node_parent_flow_by_name(self, node_name: str) -> str:
        if node_name not in self._name_to_parent_flow_name:
            msg = f"Node '{node_name}' could not be found."
            raise KeyError(msg)
        return self._name_to_parent_flow_name[node_name]

    def on_resolve_from_node_request(self, request: ResolveNodeRequest) -> ResultPayload:  # noqa: PLR0911 TODO(griptape): resolve
        node_name = request.node_name
        debug_mode = request.debug_mode

        if not node_name:
            details = "No Node name was provided. Failed to resolve node."
            print(details)  # TODO(griptape): Move to Log

            return ResolveNodeResult_Failure()
        try:
            node = GriptapeNodes.NodeManager().get_node_by_name(node_name)
        except KeyError:
            details = f'Resolve failure. "{node_name}" does not exist.'
            print(details)  # TODO(griptape): Move to Log

            return ResolveNodeResult_Failure()
        # try to get the flow parent of this node
        try:
            flow_name = self._name_to_parent_flow_name[node_name]
        except KeyError:
            details = f'Failed to fetch parent flow for "{node_name}"'
            print(details)  # TODO(griptape): Move to Log

            return ResolveNodeResult_Failure()
        try:
            obj_mgr = GriptapeNodes()._object_manager
            flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        except KeyError:
            details = f'Failed to fetch parent flow for "{node_name}"'
            print(details)  # TODO(griptape): Move to Log

            return ResolveNodeResult_Failure()

        if flow is None:
            details = f'Failed to fetch parent flow for "{node_name}"'
            return ResolveNodeResult_Failure()
        try:
            flow.connections.unresolve_future_nodes(node)
        except Exception:
            details = f'Failed to mark future nodes dirty. Unable to kick off flow from "{node_name}"'
            print(details)
            return ResolveNodeResult_Failure()
        try:
            flow.resolve_singular_node(node, debug_mode)
        except Exception as e:
            details = f'Failed to resolve "{node_name}".  Error: {e}'
            print(details)  # TODO(griptape): Move to Log

            return ResolveNodeResult_Failure()
        details = f'Starting to resolve "{node_name}" in "{flow_name}"'
        print(details)  # TODO(griptape): Move to Log
        return ResolveNodeResult_Success()

    def on_validate_node_dependencies_request(self, request:ValidateNodeDependenciesRequest) -> ResultPayload:
        node_name = request.node_name
        obj_manager = GriptapeNodes.get_instance()._object_manager
        node = obj_manager.attempt_get_object_by_name_as_type(node_name, NodeBase)
        if not node:
            details = f'Failed to validate node dependencies. Node with "{node_name}" does not exist.'
            print(details)
            return ValidateFlowDependenciesResult_Failure()
        exceptions = node.validate_node()
        return ValidateFlowDependenciesResult_Success(validation_succeeded=(exceptions is None), exceptions=exceptions if exceptions else None)


class ScriptManager:
    def __init__(self, event_manager: EventManager) -> None:
        event_manager.assign_manager_to_request_type(
            RunScriptFromScratchRequest, self.on_run_script_from_scratch_request
        )
        event_manager.assign_manager_to_request_type(
            RunScriptWithCurrentStateRequest,
            self.on_run_script_with_current_state_request,
        )
        event_manager.assign_manager_to_request_type(
            RunScriptFromRegistryRequest,
            self.on_run_script_from_registry_request,
        )
        event_manager.assign_manager_to_request_type(
            RegisterScriptRequest,
            self.on_register_script_request,
        )
        event_manager.assign_manager_to_request_type(
            ListAllScriptsRequest,
            self.on_list_all_scripts_request,
        )
        event_manager.assign_manager_to_request_type(
            DeleteScriptRequest,
            self.on_delete_scripts_request,
        )
        event_manager.assign_manager_to_request_type(
            SaveSceneRequest,
            self.on_save_scene_request,
        )

    def run_script(self, relative_file_path: str) -> tuple[bool, str]:
        relative_file_path_obj = Path(relative_file_path)
        if relative_file_path_obj.is_absolute():
            complete_file_path = relative_file_path_obj
        else:
            complete_file_path = ScriptRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        try:
            with Path(complete_file_path).open() as file:
                script_content = file.read()
            exec(script_content)  # noqa: S102
        except Exception as e:
            return (
                False,
                f"Failed to run script on path '{complete_file_path}'. Exception: {e}",
            )
        return True, f"Succeeded in running script on path '{complete_file_path}'."

    def on_run_script_from_scratch_request(self, request: RunScriptFromScratchRequest) -> ResultPayload:
        # Check if file path exists

        relative_file_path = request.file_path
        complete_file_path = ScriptRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        if not Path(complete_file_path).is_file():
            details = f"Failed to find file. Path '{complete_file_path}' doesn't exist."
            print(details)
            return RunScriptFromScratchResult_Failure()

        try:
            # Clear the existing flows
            GriptapeNodes.clear_data()
        except Exception as e:
            details = f"Failed to clear the existing context when trying to run '{complete_file_path}'. Exception: {e}"
            print(details)
            return RunScriptFromScratchResult_Failure()

        # Run the file, goddamn it
        success, details = self.run_script(relative_file_path=relative_file_path)
        print(details)
        if success:
            return RunScriptFromScratchResult_Success()
        return RunScriptFromScratchResult_Failure()

    def on_run_script_with_current_state_request(self, request: RunScriptWithCurrentStateRequest) -> ResultPayload:
        relative_file_path = request.file_path
        complete_file_path = ScriptRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        if not Path(complete_file_path).is_file():
            details = f"Failed to find file. Path '{complete_file_path}' doesn't exist."
            print(details)
            return RunScriptWithCurrentStateResult_Failure()
        success, details = self.run_script(relative_file_path=relative_file_path)
        print(details)
        if success:
            return RunScriptWithCurrentStateResult_Success()
        return RunScriptWithCurrentStateResult_Failure()

    def on_run_script_from_registry_request(self, request: RunScriptFromRegistryRequest) -> ResultPayload:
        # get script from registry
        try:
            script = ScriptRegistry.get_script_by_name(request.script_name)
        except KeyError as e:
            print(e)
            return RunScriptFromRegistryResult_Failure()
        # get file_path from script
        relative_file_path = script.relative_file_path
        # run file
        success, details = self.run_script(relative_file_path=relative_file_path)
        print(details)
        if success:
            return RunScriptFromRegistryResult_Success()
        return RunScriptFromRegistryResult_Failure()

    def on_register_script_request(self, request: RegisterScriptRequest) -> ResultPayload:
        try:
            script = ScriptRegistry.generate_new_script(
                request.script_name,
                request.file_path,
                request.description,
                request.image,
            )
        except Exception as e:
            print(f"Failed to register script with name {request.script_name}. Error: {e}")
            return RegisterScriptResult_Failure()
        return RegisterScriptResult_Success(script_name=script.name)

    def on_list_all_scripts_request(self, _request: ListAllScriptsRequest) -> ResultPayload:
        try:
            scripts = ScriptRegistry.list_scripts()
        except Exception:
            print("Failed to list all scripts.")
            return ListAllScriptsResult_Failure()
        return ListAllScriptsResult_Success(scripts=scripts)

    def on_delete_scripts_request(self, request: DeleteScriptRequest) -> ResultPayload:
        try:
            script = ScriptRegistry.delete_script_by_name(request.name)
        except Exception as e:
            print(f"Failed to remove script from registry with name {request.name}. Exception: {e}")
            return DeleteScriptResult_Failure()
        config_manager = GriptapeNodes.get_instance()._config_manager
        try:
            config_manager.delete_user_script(script.__dict__)
        except Exception as e:
            print(f"Failed to remove script from user config with name {request.name}. Exception: {e}")
            return DeleteScriptResult_Failure()
        # delete the actual file
        full_path = config_manager.workspace_path.joinpath(script.relative_file_path)
        try:
            full_path.unlink()
        except Exception as e:
            print(f"Failed to delete script file with path {script.relative_file_path}. Exception: {e}")
            return DeleteScriptResult_Failure()
        return DeleteScriptResult_Success()

    def on_save_scene_request(self, request: SaveSceneRequest) -> ResultPayload:
        obj_manager = GriptapeNodes.get_instance()._object_manager
        node_manager = GriptapeNodes.get_instance()._node_manager
        config_manager = GriptapeNodes.get_instance()._config_manager
        # open my file
        if request.file_name:
            file_name = request.file_name
        else:
            local_tz = datetime.now().astimezone().tzinfo
            file_name = datetime.now(tz=local_tz).strftime("%d.%m_%H.%M")
        relative_file_path = f"{file_name}.py"
        file_path = config_manager.workspace_path.joinpath(relative_file_path)
        created_flows = []
        try:
            with file_path.open("w") as file:
                file.write("from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes\n")
                # Write all flows to a file, get back the strings for connections
                connection_request_scripts = handle_flow_saving(file, obj_manager, created_flows)
                # Now all of the flows have been created.
                for node in obj_manager.get_filtered_subset(type=NodeBase).values():
                    flow_name = node_manager.get_node_parent_flow_by_name(node.name)
                    creation_request = CreateNodeRequest(
                        node_type=node.__class__.__name__,
                        node_name=node.name,
                        metadata=node.metadata,
                        override_parent_flow_name=flow_name,
                    )
                    code_string = f"GriptapeNodes().handle_request({creation_request})"
                    file.write(code_string + "\n")
                    # Save the parameters
                    handle_parameter_creation_saving(file, node, flow_name)
                # Now all nodes AND parameters have been created
                file.write(connection_request_scripts)
        except Exception as e:
            print(f"Failed to save scene, exception: {e}")
            return SaveSceneResult_Failure()
        # save the created scene to a personal json file
        if file_name not in ScriptRegistry.list_scripts():
            script = {
                "name": f"{file_name}",
                "relative_file_path": relative_file_path,
                "image": None,
                "description": None,
            }
            config_manager.save_user_script_json(script)
            ScriptRegistry.generate_new_script(**script)
        return SaveSceneResult_Success(file_path=str(file_path))


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
        code_string = f"GriptapeNodes().handle_request({creation_request})"
        file.write(code_string + "\n")
        created_flows.append(flow_name)

    return created_flows


def handle_flow_saving(file: TextIO, obj_manager: ObjectManager, created_flows: list) -> str:
    flow_manager = GriptapeNodes.get_instance()._flow_manager
    connection_request_scripts = ""
    for flow_name, flow in obj_manager.get_filtered_subset(type=ControlFlow).items():
        create_flows_in_order(flow_name, flow_manager, created_flows, file)
        # While creating flows - let's create all of our connections
        for connection in flow.connections.connections.values():
            creation_request = CreateConnectionRequest(
                source_node_name=connection.source_node.name,
                source_parameter_name=connection.source_parameter.name,
                target_node_name=connection.target_node.name,
                target_parameter_name=connection.target_parameter.name,
            )
            code_string = f"GriptapeNodes().handle_request({creation_request})"
            connection_request_scripts += code_string + "\n"
    return connection_request_scripts


def handle_parameter_creation_saving(file: TextIO, node: NodeBase, flow_name: str) -> None:
    for parameter in node.parameters:
        param_dict = vars(parameter)
        # Create the parameter, or alter it on the existing node
        if parameter.user_defined:
            param_dict["node_name"] = node.name
            creation_request = AddParameterToNodeRequest.create(**param_dict)
            code_string = f"GriptapeNodes().handle_request({creation_request})"
            file.write(code_string + "\n")
        else:
            diff = manage_alter_details(parameter, type(node))
            if diff:
                diff["node_name"] = node.name
                diff["parameter_name"] = parameter.name
                creation_request = AlterParameterDetailsRequest.create(**diff)
                code_string = f"GriptapeNodes().handle_request({creation_request})"
                file.write(code_string + "\n")
        if parameter.name in node.parameter_values and parameter.name not in node.parameter_output_values:
            # SetParameterValueRequest event
            code_string = handle_parameter_value_saving(parameter, node, flow_name)
            if code_string:
                file.write(code_string + "\n")


def handle_parameter_value_saving(parameter: Parameter, node: NodeBase, flow_name: str) -> str | None:
    flow_manager = GriptapeNodes()._flow_manager
    parent_flow = flow_manager.get_flow_by_name(flow_name)
    if not (
        node.name in parent_flow.connections.incoming_index
        and parameter.name in parent_flow.connections.incoming_index[node.name]
    ):
        value = node.get_parameter_value(parameter.name)
        safe_conversion = False
        if hasattr(value, "__str__") and value.__class__.__str__ is not object.__str__:
            value = str(value)
            safe_conversion = True
        # If it doesn't have a custom __str__, convert to dict if possible
        elif hasattr(value, "__dict__"):
            value = str(value.__dict__)
            safe_conversion = True
        if safe_conversion:
            creation_request = SetParameterValueRequest(
                parameter_name=parameter.name,
                node_name=node.name,
                value=value,
            )
            return f"GriptapeNodes().handle_request({creation_request})"
    return None


def manage_alter_details(parameter: Parameter, base_node: type) -> dict:
    base_node_obj = base_node(name="test")
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
            result = RunArbitraryPythonStringResult_Success(python_output=captured_output)
        except Exception as e:
            python_output = f"ERROR: {e}"
            result = RunArbitraryPythonStringResult_Failure(python_output=python_output)

        return result


class LibraryManager:
    def __init__(self, event_manager: EventManager) -> None:
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

        event_manager.add_listener_to_app_event(
            AppInitializationComplete,
            self.on_app_initialization_complete,
        )

    def on_list_registered_libraries_request(self, _request: ListRegisteredLibrariesRequest) -> ResultPayload:
        # Make a COPY of the list
        snapshot_list = LibraryRegistry.list_libraries()
        event_copy = snapshot_list.copy()

        details = "Successfully retrieved the list of registered libraries."
        print(details)  # TODO(griptape): Move to Log

        result = ListRegisteredLibrariesResult_Success(
            libraries=event_copy,
        )
        return result

    def on_list_node_types_in_library_request(self, request: ListNodeTypesInLibraryRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to list node types in a Library named '{request.library}'. Failed because no Library with that name was registered."
            print(details)  # TODO(griptape): Move to Log

            result = ListNodeTypesInLibraryResult_Failure()
            return result

        # Cool, get a copy of the list.
        snapshot_list = library.get_registered_nodes()
        event_copy = snapshot_list.copy()

        details = f"Successfully retrieved the list of node types in the Library named '{request.library}'."
        print(details)  # TODO(griptape): Move to Log

        result = ListNodeTypesInLibraryResult_Success(
            node_types=event_copy,
        )
        return result

    def get_library_metadata_request(self, request: GetLibraryMetadataRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get metadata for Library '{request.library}'. Failed because no Library with that name was registered."
            print(details)  # TODO(griptape): Move to Log

            result = GetLibraryMetadataResult_Failure()
            return result

        # Get the metadata off of it.
        metadata = library.get_metadata()
        result = GetLibraryMetadataResult_Success(metadata=metadata)
        print(f"Successfully retrieved metadata for Library '{request.library}'.")
        return result

    def get_node_metadata_from_library_request(self, request: GetNodeMetadataFromLibraryRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get node metadata for a node type '{request.node_type}' in a Library named '{request.library}'. Failed because no Library with that name was registered."
            print(details)  # TODO(griptape): Move to Log

            result = GetNodeMetadataFromLibraryResult_Failure()
            return result

        # Does the node type exist within the library?
        try:
            metadata = library.get_node_metadata(node_type=request.node_type)
        except KeyError:
            details = f"Attempted to get node metadata for a node type '{request.node_type}' in a Library named '{request.library}'. Failed because no node type of that name could be found in the Library."
            print(details)  # TODO(griptape): Move to Log

            result = GetNodeMetadataFromLibraryResult_Failure()
            return result

        details = f"Successfully retrieved node metadata for a node type '{request.node_type}' in a Library named '{request.library}'."
        print(details)  # TODO(griptape): Move to Log

        result = GetNodeMetadataFromLibraryResult_Success(
            metadata=metadata,
        )
        return result

    def list_categories_in_library_request(self, request: ListCategoriesInLibraryRequest) -> ResultPayload:
        # Does this library exist?
        try:
            library = LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get categories in a Library named '{request.library}'. Failed because no Library with that name was registered."
            print(details)  # TODO(griptape): Move to Log
            result = ListCategoriesInLibraryResult_Failure()
            return result

        categories = library.get_categories()
        result = ListCategoriesInLibraryResult_Success(categories=categories)
        return result

    def register_library_from_file_request(self, request: RegisterLibraryFromFileRequest) -> ResultPayload:
        file_path = request.file_path

        # Convert to Path object if it's a string
        json_path = Path(file_path)

        # Check if the file exists
        if not json_path.exists():
            print(
                f"Attempted to load Library JSON file. Failed because no file could be found at the specified path: {json_path}"
            )  # TODO(griptape): Move to Log
            return RegisterLibraryFromFileResult_Failure()

        # Load the JSON
        with json_path.open("r") as f:
            library_data = json.load(f)

        # Extract library information
        try:
            library_name = library_data["name"]
            library_metadata = library_data.get("metadata", {})
            nodes_metadata = library_data.get("nodes", [])
        except KeyError as e:
            print(
                f"Attempted to load Library JSON file from '{file_path}'. Failed because it was missing required field in library metadata: {e}"
            )  # TODO(griptape): Move to Log
            return RegisterLibraryFromFileResult_Failure()

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
            print(
                f"Attempted to load Library JSON file from '{file_path}'. Failed because a Library '{library_name}' already exists. Error: {err}."
            )  # TODO(griptape): Move to Log
            return RegisterLibraryFromFileResult_Failure()

        # Update library metadata
        library._metadata = library_metadata

        # Process each node in the metadata
        for node_meta in nodes_metadata:
            try:
                class_name = node_meta["class_name"]
                file_path = node_meta["file_path"]
                node_metadata = node_meta.get("metadata", {})

                # Resolve relative path to absolute path
                file_path = Path(file_path)
                if not file_path.is_absolute():
                    file_path = base_dir / file_path

                # Dynamically load the module containing the node class
                node_class = self._load_class_from_file(file_path, class_name)

                # Register the node type with the library
                library.register_new_node_type(node_class, metadata=node_metadata)

            except (KeyError, ImportError, AttributeError) as e:
                print(
                    f"Attempted to load Library JSON file from '{file_path}'. Failed due to an error loading node {node_meta.get('class_name', 'unknown')}: {e}"
                )  # TODO(griptape): MOVE TO LOG
                return RegisterLibraryFromFileResult_Failure()

        # Success!
        print(f"Successfully loaded Library '{library_name}' from JSON file at {file_path}")
        return RegisterLibraryFromFileResult_Success(library_name=library_name)

    def get_all_info_for_all_libraries_request(self, request: GetAllInfoForAllLibrariesRequest) -> ResultPayload:  # noqa: ARG002
        list_libraries_request = ListRegisteredLibrariesRequest()
        list_libraries_result = self.on_list_registered_libraries_request(list_libraries_request)

        if not list_libraries_result.succeeded():
            details = "Attempted to get all info for all libraries, but listing the registered libraries failed."
            print(details)  # TODO(griptape): Move to Log
            return GetAllInfoForAllLibrariesResult_Failure()

        try:
            list_libraries_success = cast("ListRegisteredLibrariesResult_Success", list_libraries_result)

            # Create a mapping of library name to all its info.
            library_name_to_all_info = {}

            for library_name in list_libraries_success.libraries:
                library_all_info_request = GetAllInfoForLibraryRequest(library=library_name)
                library_all_info_result = self.get_all_info_for_library_request(library_all_info_request)

                if not library_all_info_result.succeeded():
                    details = f"Attempted to get all info for all libraries, but failed when getting all info for library named '{library_name}'."
                    print(details)  # TODO(griptape): Move to Log
                    return GetAllInfoForAllLibrariesResult_Failure()

                library_all_info_success = cast("GetAllInfoForLibraryResult_Success", library_all_info_result)

                library_name_to_all_info[library_name] = library_all_info_success
        except Exception as err:
            details = f"Attempted to get all info for all libraries. Encountered error {err}."
            print(details)  # TODO(griptape): Move to Log
            return GetAllInfoForAllLibrariesResult_Failure()

        # We're home free now
        details = "Successfully retrieved all info for all libraries."
        print(details)  # TODO(griptape): Move to Log
        result = GetAllInfoForAllLibrariesResult_Success(library_name_to_library_info=library_name_to_all_info)
        return result

    def get_all_info_for_library_request(self, request: GetAllInfoForLibraryRequest) -> ResultPayload:  # noqa: PLR0911
        # Does this library exist?
        try:
            LibraryRegistry.get_library(name=request.library)
        except KeyError:
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed because no Library with that name was registered."
            print(details)  # TODO(griptape): Move to Log
            result = GetAllInfoForLibraryResult_Failure()
            return result

        library_metadata_request = GetLibraryMetadataRequest(library=request.library)
        library_metadata_result = self.get_library_metadata_request(library_metadata_request)

        if not library_metadata_result.succeeded():
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the library's metadata."
            print(details)  # TODO(griptape): Move to Log
            return GetAllInfoForLibraryResult_Failure()

        list_categories_request = ListCategoriesInLibraryRequest(library=request.library)
        list_categories_result = self.list_categories_in_library_request(list_categories_request)

        if not list_categories_result.succeeded():
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the list of categories in the library."
            print(details)  # TODO(griptape): Move to Log
            return GetAllInfoForLibraryResult_Failure()

        node_type_list_request = ListNodeTypesInLibraryRequest(library=request.library)
        node_type_list_result = self.on_list_node_types_in_library_request(node_type_list_request)

        if not node_type_list_result.succeeded():
            details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the list of node types in the library."
            print(details)  # TODO(griptape): Move to Log
            return GetAllInfoForLibraryResult_Failure()

        # Cast everyone to their success counterparts.
        try:
            library_metadata_result_success = cast("GetLibraryMetadataResult_Success", library_metadata_result)
            list_categories_result_success = cast("ListCategoriesInLibraryResult_Success", list_categories_result)
            node_type_list_result_success = cast("ListNodeTypesInLibraryResult_Success", node_type_list_result)
        except Exception as err:
            details = (
                f"Attempted to get all library info for a Library named '{request.library}'. Encountered error: {err}."
            )
            print(details)  # TODO(griptape): Move to Log
            return GetAllInfoForLibraryResult_Failure()

        # Now build the map of node types to metadata.
        node_type_name_to_node_metadata_details = {}
        for node_type_name in node_type_list_result_success.node_types:
            node_metadata_request = GetNodeMetadataFromLibraryRequest(library=request.library, node_type=node_type_name)
            node_metadata_result = self.get_node_metadata_from_library_request(node_metadata_request)

            if not node_metadata_result.succeeded():
                details = f"Attempted to get all library info for a Library named '{request.library}'. Failed attempting to get the metadata for a node type called '{node_type_name}'."
                print(details)  # TODO(griptape): Move to Log
                return GetAllInfoForLibraryResult_Failure()

            try:
                node_metadata_result_success = cast("GetNodeMetadataFromLibraryResult_Success", node_metadata_result)
            except Exception as err:
                details = f"Attempted to get all library info for a Library named '{request.library}'. Encountered error: {err}."
                print(details)  # TODO(griptape): Move to Log
                return GetAllInfoForLibraryResult_Failure()

            # Put it into the map.
            node_type_name_to_node_metadata_details[node_type_name] = node_metadata_result_success

        details = f"Successfully got all library info for a Library named '{request.library}'."
        print(details)  # TODO(griptape): Move to Log
        result = GetAllInfoForLibraryResult_Success(
            library_metadata_details=library_metadata_result_success,
            category_details=list_categories_result_success,
            node_type_name_to_node_metadata_details=node_type_name_to_node_metadata_details,
        )
        return result

    def _load_class_from_file(self, file_path: Path | str, class_name: str) -> type[NodeBase]:
        """Dynamically load a class from a Python file.

        Args:
            file_path: Path to the Python file
            class_name: Name of the class to load

        Returns:
            The loaded class

        Raises:
            ImportError: If the module cannot be imported
            AttributeError: If the class doesn't exist in the module
        """
        # Ensure file_path is a Path object
        file_path = Path(file_path)

        # Generate a unique module name
        module_name = f"dynamic_module_{file_path.name.replace('.', '_')}_{hash(str(file_path))}"

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
        spec.loader.exec_module(module)

        # Get the class
        try:
            node_class = getattr(module, class_name)
        except AttributeError as e:
            msg = f"Class '{class_name}' not found in module {file_path}"
            raise AttributeError(msg) from e

        # Verify it's a NodeBase subclass
        if not issubclass(node_class, NodeBase):
            msg = f"{class_name} must inherit from NodeBase"
            raise TypeError(msg)

        return node_class

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        # App just got init'd. See if there are library JSONs to load!
        default_libraries_section = (
            "app_events_internal.on_app_initialization_complete.paths_to_library_json_files_to_register"
        )
        self._load_libraries_from_config_category(
            config_category=default_libraries_section, load_as_default_library=True
        )

        # Now load the user libraries (they don't get special "default library" treatment)
        user_libraries_section = "app_events.on_app_initialization_complete.paths_to_library_json_files_to_register"
        self._load_libraries_from_config_category(config_category=user_libraries_section, load_as_default_library=False)

        # See if there are script JSONs to load!
        user_script_section = "app_events.on_app_initialization_complete.scripts_to_register"
        self._register_scripts_from_config(config_section=user_script_section, location_default=False)
        default_script_section = "app_events_internal.on_app_initialization_complete.scripts_to_register"
        self._register_scripts_from_config(config_section=default_script_section, location_default=True)
        # See if there are user JSONs to load!

    def _load_libraries_from_config_category(self, config_category: str, load_as_default_library: bool) -> None:  # noqa: FBT001
        config_mgr = GriptapeNodes().ConfigManager()
        libraries_to_register_category = config_mgr.get_config_value(config_category)

        if libraries_to_register_category is not None:
            for library_to_register in libraries_to_register_category:
                library_load_request = RegisterLibraryFromFileRequest(
                    file_path=library_to_register,
                    load_as_default_library=load_as_default_library,
                )
                GriptapeNodes().handle_request(library_load_request)

    def _register_scripts_from_config(self, config_section: str, location_default: bool) -> None:  # noqa: FBT001
        config_mgr = GriptapeNodes().ConfigManager()
        scripts_to_register = config_mgr.get_config_value(config_section)
        if scripts_to_register is not None:
            for script in scripts_to_register:
                if location_default:
                    file_path = Path.cwd().joinpath(script["relative_file_path"])
                    script_register_request = RegisterScriptRequest(
                        script_name=script["name"],
                        file_path=str(file_path),
                        description=script["description"],
                        image=script["image"],
                    )
                    GriptapeNodes().handle_request(script_register_request)
                else:
                    script_register_request = RegisterScriptRequest(
                        script_name=script["name"],
                        file_path=script["relative_file_path"],
                        description=script["description"],
                        image=script["image"],
                    )
                    GriptapeNodes().handle_request(script_register_request)


@dataclass
class OperationStepList:
    operation_id: int
    step_events: list[str] = field(default_factory=list)


# TODO(griptape): Update this with breaking changes in event manager
class LogManager:
    _operations: list[OperationStepList]

    def __init__(self, _event_manager: EventManager) -> None:
        self._operations: list[OperationStepList] = []
        self._next_operation_index = 0

    def on_event(self, event: EventBase) -> None:
        # If this is a TOP-LEVEL event, then we treat it as a new "operation", otherwise it's a "step"
        event_depth = GriptapeNodes().EventManager().get_operation_depth()

        target_list = None
        if event_depth == 0:
            new_list = OperationStepList(operation_id=self._next_operation_index)
            self._operations.append(new_list)
            self._next_operation_index += 1

            target_list = new_list
        else:
            # Get the most recent one.
            target_list = self._operations[-1]

        target_list.step_events.append(type(event).__name__)
