from __future__ import annotations

import importlib.util
import io
import json
import logging
import re
import sys
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from re import Pattern
from typing import Any, ClassVar, TextIO, TypeVar, cast

import tomlkit
from dotenv import load_dotenv
from rich.logging import RichHandler
from xdg_base_dirs import xdg_data_home

from griptape_nodes.exe_types.core_types import (
    BaseNodeElement,
    Parameter,
    ParameterContainer,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.node_library.workflow_registry import LibraryNameAndVersion, WorkflowMetadata, WorkflowRegistry
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
    ResultPayloadFailure,
)
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    CreateConnectionResultFailure,
    CreateConnectionResultSuccess,
    DeleteConnectionRequest,
    DeleteConnectionResultFailure,
    DeleteConnectionResultSuccess,
    IncomingConnection,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultFailure,
    ListConnectionsForNodeResultSuccess,
    OutgoingConnection,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CancelFlowRequest,
    CancelFlowResultFailure,
    CancelFlowResultSuccess,
    ContinueExecutionStepRequest,
    ContinueExecutionStepResultFailure,
    ContinueExecutionStepResultSuccess,
    GetFlowStateRequest,
    GetFlowStateResultFailure,
    GetFlowStateResultSuccess,
    GetIsFlowRunningRequest,
    GetIsFlowRunningResultFailure,
    GetIsFlowRunningResultSuccess,
    ResolveNodeRequest,
    ResolveNodeResultFailure,
    ResolveNodeResultSuccess,
    SingleExecutionStepRequest,
    SingleExecutionStepResultFailure,
    SingleExecutionStepResultSuccess,
    SingleNodeStepRequest,
    SingleNodeStepResultFailure,
    SingleNodeStepResultSuccess,
    StartFlowRequest,
    StartFlowResultFailure,
    StartFlowResultSuccess,
    UnresolveFlowRequest,
    UnresolveFlowResultFailure,
    UnresolveFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    CreateFlowResultFailure,
    CreateFlowResultSuccess,
    DeleteFlowRequest,
    DeleteFlowResultFailure,
    DeleteFlowResultSuccess,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
    ListFlowsInCurrentContextRequest,
    ListFlowsInCurrentContextResultFailure,
    ListFlowsInCurrentContextResultSuccess,
    ListFlowsInFlowRequest,
    ListFlowsInFlowResultFailure,
    ListFlowsInFlowResultSuccess,
    ListNodesInFlowRequest,
    ListNodesInFlowResultFailure,
    ListNodesInFlowResultSuccess,
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
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResultFailure,
    CreateNodeResultSuccess,
    DeleteNodeRequest,
    DeleteNodeResultFailure,
    DeleteNodeResultSuccess,
    GetAllNodeInfoRequest,
    GetAllNodeInfoResultFailure,
    GetAllNodeInfoResultSuccess,
    GetNodeMetadataRequest,
    GetNodeMetadataResultFailure,
    GetNodeMetadataResultSuccess,
    GetNodeResolutionStateRequest,
    GetNodeResolutionStateResultFailure,
    GetNodeResolutionStateResultSuccess,
    ListParametersOnNodeRequest,
    ListParametersOnNodeResultFailure,
    ListParametersOnNodeResultSuccess,
    SetNodeMetadataRequest,
    SetNodeMetadataResultFailure,
    SetNodeMetadataResultSuccess,
)
from griptape_nodes.retained_mode.events.object_events import (
    ClearAllObjectStateRequest,
    ClearAllObjectStateResultFailure,
    ClearAllObjectStateResultSuccess,
    RenameObjectRequest,
    RenameObjectResultFailure,
    RenameObjectResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AddParameterToNodeResultFailure,
    AddParameterToNodeResultSuccess,
    AlterParameterDetailsRequest,
    AlterParameterDetailsResultFailure,
    AlterParameterDetailsResultSuccess,
    GetCompatibleParametersRequest,
    GetCompatibleParametersResultFailure,
    GetCompatibleParametersResultSuccess,
    GetNodeElementDetailsRequest,
    GetNodeElementDetailsResultFailure,
    GetNodeElementDetailsResultSuccess,
    GetParameterDetailsRequest,
    GetParameterDetailsResultFailure,
    GetParameterDetailsResultSuccess,
    GetParameterValueRequest,
    GetParameterValueResultFailure,
    GetParameterValueResultSuccess,
    ParameterAndMode,
    RemoveParameterFromNodeRequest,
    RemoveParameterFromNodeResultFailure,
    RemoveParameterFromNodeResultSuccess,
    SetParameterValueRequest,
    SetParameterValueResultFailure,
    SetParameterValueResultSuccess,
)
from griptape_nodes.retained_mode.events.validation_events import (
    ValidateFlowDependenciesRequest,
    ValidateFlowDependenciesResultFailure,
    ValidateFlowDependenciesResultSuccess,
    ValidateNodeDependenciesRequest,
    ValidateNodeDependenciesResultFailure,
    ValidateNodeDependenciesResultSuccess,
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
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.context_manager import ContextManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.operation_manager import OperationDepthManager
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
from griptape_nodes.retained_mode.managers.settings import WorkflowSettingsDetail

load_dotenv()

T = TypeVar("T")


logger = logging.getLogger("griptape_nodes")
logger.setLevel(logging.INFO)

logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))


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
        return event_mgr.handle_request(request=request, operation_depth_mgr=obj_depth_mgr)

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

            match = re.match(r"(\d+)\.(\d+)\.(\d+)", engine_version_str)
            if match:
                major, minor, patch = map(int, match.groups())
                return GetEngineVersionResultSuccess(major=major, minor=minor, patch=patch)
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


OBJ_TYPE = TypeVar("OBJ_TYPE")


class ObjectManager:
    _name_to_objects: dict[str, object]

    def __init__(self, _event_manager: EventManager) -> None:
        self._name_to_objects = {}
        _event_manager.assign_manager_to_request_type(
            request_type=RenameObjectRequest, callback=self.on_rename_object_request
        )
        _event_manager.assign_manager_to_request_type(
            request_type=ClearAllObjectStateRequest, callback=self.on_clear_all_object_state_request
        )

    def on_rename_object_request(self, request: RenameObjectRequest) -> ResultPayload:
        # Does the source object exist?
        source_obj = self.attempt_get_object_by_name(request.object_name)
        if source_obj is None:
            details = f"Attempted to rename object '{request.object_name}', but no object of that name could be found."
            logger.error(details)
            return RenameObjectResultFailure(next_available_name=None)

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
                logger.error(details)
                return RenameObjectResultFailure(next_available_name=next_name)
            # We'll use the next available name.
            final_name = next_name

        # Let the object's manager know. TODO(griptape): find a better way than a bunch of special cases.
        match source_obj:
            case ControlFlow():
                GriptapeNodes.FlowManager().handle_flow_rename(old_name=request.object_name, new_name=final_name)
            case BaseNode():
                GriptapeNodes.NodeManager().handle_node_rename(old_name=request.object_name, new_name=final_name)
            case _:
                details = f"Attempted to rename an object named '{request.object_name}', but that object wasn't of a type supported for rename."
                logger.error(details)
                return RenameObjectResultFailure(next_available_name=None)

        # Update the object table.
        self._name_to_objects[final_name] = source_obj
        del self._name_to_objects[request.object_name]

        details = f"Successfully renamed object '{request.object_name}' to '{final_name}`."
        log_level = logging.DEBUG
        if final_name != request.requested_name:
            details += " WARNING: Originally requested the name '{request.requested_name}', but that was taken."
            log_level = logging.WARNING
        logger.log(level=log_level, msg=details)
        return RenameObjectResultSuccess(final_name=final_name)

    def on_clear_all_object_state_request(self, request: ClearAllObjectStateRequest) -> ResultPayload:
        if not request.i_know_what_im_doing:
            logger.warning(
                "Attempted to clear all object state and delete everything. Failed because they didn't know what they were doing."
            )
            return ClearAllObjectStateResultFailure()
        # Let's try and clear it all.
        context_mgr = GriptapeNodes.ContextManager()
        while context_mgr.has_current_flow():
            while context_mgr.has_current_node():
                context_mgr.pop_node()
            context_mgr.pop_flow()

        try:
            # Clear the existing flows, which will clear all nodes and connections.
            GriptapeNodes.clear_data()
        except Exception as e:
            details = f"Attempted to clear all object state and delete everything. Failed with exception: {e}"
            logger.error(details)
            return ClearAllObjectStateResultFailure()

        details = "Successfully cleared all object state (deleted everything)."
        logger.debug(details)
        return ClearAllObjectStateResultSuccess()

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
        return self._name_to_objects.get(name, None)

    def attempt_get_object_by_name_as_type(self, name: str, cast_type: type[T]) -> T | None:
        obj = self.attempt_get_object_by_name(name)
        if obj is not None and isinstance(obj, cast_type):
            return obj
        return None

    def del_obj_by_name(self, name: str) -> None:
        # Does the object have any children? delete those
        obj = self._name_to_objects[name]
        if isinstance(obj, BaseNodeElement):
            children = obj.find_elements_by_type(BaseNodeElement)
            for child in children:
                obj.remove_child(child)
                if isinstance(child, BaseNode):
                    GriptapeNodes.handle_request(DeleteNodeRequest(child.name))
                    return
                if isinstance(child, Parameter) and isinstance(obj, BaseNode):
                    GriptapeNodes.handle_request(RemoveParameterFromNodeRequest(child.name, obj.name))
                    return
        del self._name_to_objects[name]


class FlowManager:
    _name_to_parent_name: dict[str, str | None]

    def __init__(self, event_manager: EventManager) -> None:
        event_manager.assign_manager_to_request_type(CreateFlowRequest, self.on_create_flow_request)
        event_manager.assign_manager_to_request_type(DeleteFlowRequest, self.on_delete_flow_request)
        event_manager.assign_manager_to_request_type(ListNodesInFlowRequest, self.on_list_nodes_in_flow_request)
        event_manager.assign_manager_to_request_type(ListFlowsInFlowRequest, self.on_list_flows_in_flow_request)
        event_manager.assign_manager_to_request_type(
            ListFlowsInCurrentContextRequest, self.on_list_flows_in_current_context_request
        )
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
        event_manager.assign_manager_to_request_type(
            ValidateFlowDependenciesRequest, self.on_validate_flow_dependencies_request
        )
        event_manager.assign_manager_to_request_type(GetTopLevelFlowRequest, self.on_get_top_level_flow_request)

        self._name_to_parent_name = {}

    def get_parent_flow(self, flow_name: str) -> str | None:
        if flow_name in self._name_to_parent_name:
            return self._name_to_parent_name[flow_name]
        msg = f"Flow with name {flow_name} doesn't exist"
        raise ValueError(msg)

    def on_get_top_level_flow_request(self, request: GetTopLevelFlowRequest) -> ResultPayload:  # noqa: ARG002 (the request has to be assigned to the method)
        for flow_name, parent in self._name_to_parent_name.items():
            if parent is None:
                return GetTopLevelFlowResultSuccess(flow_name=flow_name)
        msg = "Attempted to get top level flow, but no such flow exists"
        logger.debug(msg)
        return GetTopLevelFlowResultSuccess(flow_name=None)

    def does_canvas_exist(self) -> bool:
        """Determines if there is already an existing flow with no parent flow.Returns True if there is an existing flow with no parent flow.Return False if there is no existing flow with no parent flow."""
        return any([parent is None for parent in self._name_to_parent_name.values()])  # noqa: C419

    def on_create_flow_request(self, request: CreateFlowRequest) -> ResultPayload:
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        # Who is the parent?
        parent_name = request.parent_flow_name

        # This one's tricky. If they said "None" for the parent, they could either be saying:
        # 1. Use whatever the current context is to be the parent.
        # 2. Create me as the canvas (i.e., the top-level flow, of which there can be only one)

        # We'll explore #1 first by seeing if the Context Manager already has a current flow,
        # which would mean the canvas is already established:
        if (parent_name is None) and (GriptapeNodes.ContextManager().has_current_flow()):
            # Aha! Just use that.
            parent_name = GriptapeNodes.ContextManager().get_current_flow_name()

        parent = obj_mgr.attempt_get_object_by_name_as_type(parent_name, ControlFlow)
        if parent_name is None:
            # We're trying to create the canvas. Ensure that parent does NOT already exist.
            if self.does_canvas_exist():
                details = "Attempted to create a Flow as the Canvas (top-level Flow with no parents), but the Canvas already exists."
                logger.error(details)
                result = CreateFlowResultFailure()
                return result
        # That parent exists, right?
        elif parent is None:
            details = f"Attempted to create a Flow with a parent '{request.parent_flow_name}', but no parent with that name could be found."
            logger.error(details)

            result = CreateFlowResultFailure()

            return result

        # Create it.
        final_flow_name = obj_mgr.generate_name_for_object(type_name="ControlFlow", requested_name=request.flow_name)
        flow = ControlFlow()
        obj_mgr.add_object_by_name(name=final_flow_name, obj=flow)
        self._name_to_parent_name[final_flow_name] = parent_name

        # See if we need to push it as the current context.
        if request.set_as_new_context:
            GriptapeNodes.ContextManager().push_flow(final_flow_name)

        # Success
        details = f"Successfully created Flow '{final_flow_name}'."
        log_level = logging.DEBUG
        if (request.flow_name is not None) and (final_flow_name != request.flow_name):
            details = f"{details} WARNING: Had to rename from original Flow requested '{request.flow_name}' as an object with this name already existed."
            log_level = logging.WARNING

        logger.log(level=log_level, msg=details)
        result = CreateFlowResultSuccess(flow_name=final_flow_name)
        return result

    def on_delete_flow_request(self, request: DeleteFlowRequest) -> ResultPayload:  # noqa: PLR0911 (complex af)
        flow_name = request.flow_name
        if flow_name is None:
            # We want to delete whatever is at the top of the Current Context.
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = (
                    "Attempted to delete a Flow from the Current Context. Failed because the Current Context was empty."
                )
                logger.error(details)
                result = DeleteFlowResultFailure()
                return result
            # We pop it off here, but we'll re-add it using context in a moment.
            flow_name = GriptapeNodes.ContextManager().pop_flow()

        # Does this Flow even exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is None:
            details = f"Attempted to delete Flow '{flow_name}', but no Flow with that name could be found."
            logger.error(details)
            result = DeleteFlowResultFailure()
            return result

        # Let this Flow assume the Current Context while we delete everything within it.
        with GriptapeNodes.ContextManager().flow(flow_name=flow_name):
            # Delete all child nodes in this Flow.
            list_nodes_request = ListNodesInFlowRequest()
            list_nodes_result = GriptapeNodes().handle_request(list_nodes_request)
            if isinstance(list_nodes_result, ListNodesInFlowResultFailure):
                details = f"Attempted to delete Flow '{flow_name}', but failed while attempting to get the list of Nodes owned by this Flow."
                logger.error(details)
                result = DeleteFlowResultFailure()
                return result

            node_names = list_nodes_result.node_names
            for node_name in node_names:
                delete_node_request = DeleteNodeRequest(node_name=node_name)
                delete_node_result = GriptapeNodes().handle_request(delete_node_request)
                if isinstance(delete_node_result, DeleteNodeResultFailure):
                    details = f"Attempted to delete Flow '{flow_name}', but failed while attempting to delete child Node '{node_name}'."
                    logger.error(details)
                    result = DeleteFlowResultFailure()
                    return result

            # Delete all child Flows of this Flow.
            # Note: We use ListFlowsInCurrentContextRequest here instead of ListFlowsInFlowRequest(parent_flow_name=None)
            # because None in ListFlowsInFlowRequest means "get canvas/top-level flows". We want the flows in the
            # current context, which is the flow we're deleting.
            list_flows_request = ListFlowsInCurrentContextRequest()
            list_flows_result = GriptapeNodes().handle_request(list_flows_request)
            if isinstance(list_flows_result, ListFlowsInCurrentContextResultFailure):
                details = f"Attempted to delete Flow '{flow_name}', but failed while attempting to get the list of Flows owned by this Flow."
                logger.error(details)
                result = DeleteFlowResultFailure()
                return result
            flow_names = list_flows_result.flow_names
            for child_flow_name in flow_names:
                with GriptapeNodes.ContextManager().flow(flow_name=child_flow_name):
                    # Delete them.
                    delete_flow_request = DeleteFlowRequest()
                    delete_flow_result = GriptapeNodes().handle_request(delete_flow_request)
                    if isinstance(delete_flow_result, DeleteFlowResultFailure):
                        details = f"Attempted to delete Flow '{flow_name}', but failed while attempting to delete child Flow '{child_flow_name}'."
                        logger.error(details)
                        result = DeleteFlowResultFailure()
                        return result

            # If we've made it this far, we have deleted all the children Flows and their nodes.
            # Remove the flow from our map.
            obj_mgr.del_obj_by_name(flow_name)
            del self._name_to_parent_name[flow_name]

        details = f"Successfully deleted Flow '{flow_name}'."
        logger.debug(details)
        result = DeleteFlowResultSuccess()
        return result

    def on_get_is_flow_running_request(self, request: GetIsFlowRunningRequest) -> ResultPayload:
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(request.flow_name, ControlFlow)
        if flow is None:
            details = f"Attempted to get Flow '{request.flow_name}', but no Flow with that name could be found."
            logger.error(details)
            result = GetIsFlowRunningResultFailure()
            return result
        try:
            is_running = flow.check_for_existing_running_flow()
        except Exception:
            details = f"Error while trying to get status of '{request.flow_name}'."
            logger.error(details)
            result = GetIsFlowRunningResultFailure()
            return result
        return GetIsFlowRunningResultSuccess(is_running=is_running)

    def on_list_nodes_in_flow_request(self, request: ListNodesInFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if flow_name is None:
            # First check if we have a current flow
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to list Nodes in a Flow in the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                result = ListNodesInFlowResultFailure()
                return result
            # Get the current flow from context
            flow_name = GriptapeNodes.ContextManager().get_current_flow_name()

        # Does this Flow even exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is None:
            details = (
                f"Attempted to list Nodes in Flow '{flow_name}'. Failed because no Flow with that name could be found."
            )
            logger.error(details)
            result = ListNodesInFlowResultFailure()
            return result

        ret_list = list(flow.nodes.keys())
        details = f"Successfully got the list of Nodes within Flow '{flow_name}'."
        logger.debug(details)

        result = ListNodesInFlowResultSuccess(node_names=ret_list)
        return result

    def on_list_flows_in_flow_request(self, request: ListFlowsInFlowRequest) -> ResultPayload:
        if request.parent_flow_name is not None:
            # Does this Flow even exist?
            obj_mgr = GriptapeNodes().get_instance().ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(request.parent_flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to list Flows that are children of Flow '{request.parent_flow_name}', but no Flow with that name could be found."
                logger.error(details)
                result = ListFlowsInFlowResultFailure()
                return result

        # Create a list of all child flow names that point DIRECTLY to us.
        ret_list = []
        for flow_name, parent_name in self._name_to_parent_name.items():
            if parent_name == request.parent_flow_name:
                ret_list.append(flow_name)

        details = f"Successfully got the list of Flows that are direct children of Flow '{request.parent_flow_name}'."
        logger.debug(details)

        result = ListFlowsInFlowResultSuccess(flow_names=ret_list)
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
        except ValueError as err:
            details = f'Connection failed: "{request.source_node_name}" does not exist. Error: {err}.'
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result

        target_node = None
        try:
            target_node = GriptapeNodes.NodeManager().get_node_by_name(request.target_node_name)
        except ValueError as err:
            details = f'Connection failed: "{request.target_node_name}" does not exist. Error: {err}.'
            logger.error(details)
            result = CreateConnectionResultFailure()
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
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(request.target_node_name)
            GriptapeNodes.FlowManager().get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}" failed: {err}.'
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result

        # CURRENT RESTRICTION: Now vet the parents are in the same Flow (yes this sucks)
        if target_flow_name != source_flow_name:
            details = f'Connection "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}" failed: Different flows.'
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection failed: "{request.source_node_name}.{request.source_parameter_name}" not found'
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            # TODO(griptape): We may make this a special type of failure, or attempt to handle it gracefully.
            details = f'Connection failed: "{request.target_node_name}.{request.target_parameter_name}" not found'
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result
        # Validate parameter modes accept this type of connection.
        source_modes_allowed = source_param.allowed_modes
        if ParameterMode.OUTPUT not in source_modes_allowed:
            details = f'Connection failed: "{request.source_node_name}.{request.source_parameter_name}" is not an allowed OUTPUT'
            logger.error(details)
            result = CreateConnectionResultFailure()
            return result

        target_modes_allowed = target_param.allowed_modes
        if ParameterMode.INPUT not in target_modes_allowed:
            details = f'Connection failed: "{request.target_node_name}.{request.target_parameter_name}" is not an allowed INPUT'
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result

        # Validate that the data type from the source is allowed by the target.
        if not target_param.is_incoming_type_allowed(source_param.output_type):
            details = f'Connection failed on type mismatch "{request.source_node_name}.{request.source_parameter_name}" type({source_param.output_type}) to "{request.target_node_name}.{request.target_parameter_name}" types({target_param.input_types}) '
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result

        # Ask each node involved to bless this union.
        if not source_node.allow_outgoing_connection(
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection failed : "{request.source_node_name}.{request.source_parameter_name}" rejected the connection '
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result

        if not target_node.allow_incoming_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        ):
            details = f'Connection failed : "{request.target_node_name}.{request.target_parameter_name}" rejected the connection '
            logger.error(details)

            result = CreateConnectionResultFailure()
            return result

        # Based on user feedback, if a connection already exists in a scenario where only ONE such connection can exist
        # (e.g., connecting to a data input that already has a connection, or from a control output that is already wired up),
        # delete the old connection and replace it with this one.
        old_source_node_name = None
        old_source_param_name = None
        old_target_node_name = None
        old_target_param_name = None

        # Some scenarios restrict when we can have more than one connection. See if we're in such a scenario and replace the
        # existing connection instead of adding a new one.
        connection_mgr = source_flow.connections
        # Try the OUTGOING restricted scenario first.
        restricted_scenario_connection = connection_mgr.get_existing_connection_for_restricted_scenario(
            node=source_node, parameter=source_param, is_source=True
        )
        if not restricted_scenario_connection:
            # Check the INCOMING scenario.
            restricted_scenario_connection = connection_mgr.get_existing_connection_for_restricted_scenario(
                node=target_node, parameter=target_param, is_source=False
            )

        if restricted_scenario_connection:
            # Record the original data in case we need to back out of this.
            old_source_node_name = restricted_scenario_connection.source_node.name
            old_source_param_name = restricted_scenario_connection.source_parameter.name
            old_target_node_name = restricted_scenario_connection.target_node.name
            old_target_param_name = restricted_scenario_connection.target_parameter.name

            delete_old_request = DeleteConnectionRequest(
                source_node_name=old_source_node_name,
                source_parameter_name=old_source_param_name,
                target_node_name=old_target_node_name,
                target_parameter_name=old_target_param_name,
            )
            delete_old_result = GriptapeNodes.handle_request(delete_old_request)
            if delete_old_result.failed():
                details = f"Attempted to connect '{request.source_node_name}.{request.source_parameter_name}'. Failed because there was a previous connection from '{old_source_node_name}.{old_source_param_name}' to '{old_target_node_name}.{old_target_param_name}' that could not be deleted."
                logger.error(details)
                result = CreateConnectionResultFailure()
                return result

            details = f"Deleted the previous connection from '{old_source_node_name}.{old_source_param_name}' to '{old_target_node_name}.{old_target_param_name}' to make room for the new connection."
            logger.debug(details)
        try:
            # Actually create the Connection.
            source_flow.add_connection(
                source_node=source_node,
                source_parameter=source_param,
                target_node=target_node,
                target_parameter=target_param,
            )
        except ValueError as e:
            details = f'Connection failed: "{e}"'
            logger.error(details)

            # Attempt to restore any old connection that may have been present.
            if (
                (old_source_node_name is not None)
                and (old_source_param_name is not None)
                and (old_target_node_name is not None)
                and (old_target_param_name is not None)
            ):
                create_old_connection_request = CreateConnectionRequest(
                    source_node_name=old_source_node_name,
                    source_parameter_name=old_source_param_name,
                    target_node_name=old_target_node_name,
                    target_parameter_name=old_target_param_name,
                    initial_setup=request.initial_setup,
                )
                create_old_connection_result = GriptapeNodes.handle_request(create_old_connection_request)
                if create_old_connection_result.failed():
                    details = "Failed attempting to restore the old Connection after failing the replacement. A thousand pardons."
                    logger.error(details)
            return CreateConnectionResultFailure()

        # Let the source make any internal handling decisions now that the Connection has been made.
        source_node.after_outgoing_connection(
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        )

        # And target.
        target_node.after_incoming_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        )

        details = f'Connected "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}"'
        logger.debug(details)

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
            if isinstance(target_param, ParameterContainer):
                target_node.kill_parameter_children(target_param)
        # if it existed somewhere and actually has a value - Set the parameter!
        if value and request.initial_setup is False:
            GriptapeNodes.handle_request(
                SetParameterValueRequest(
                    parameter_name=target_param.name,
                    node_name=target_node.name,
                    value=value,
                    data_type=source_param.type,
                )
            )

        result = CreateConnectionResultSuccess()

        return result

    def on_delete_connection_request(self, request: DeleteConnectionRequest) -> ResultPayload:  # noqa: PLR0911, PLR0915, C901 TODO(griptape): resolve
        # Vet the two nodes first.
        source_node = None
        try:
            source_node = GriptapeNodes.NodeManager().get_node_by_name(request.source_node_name)
        except ValueError as err:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". Error: {err}'
            logger.error(details)

            result = DeleteConnectionResultFailure()
            return result

        target_node = None
        try:
            target_node = GriptapeNodes.NodeManager().get_node_by_name(request.target_node_name)
        except ValueError as err:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". Error: {err}'
            logger.error(details)

            result = DeleteConnectionResultFailure()
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
            logger.error(details)

            result = DeleteConnectionResultFailure()
            return result

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(request.target_node_name)
            GriptapeNodes.FlowManager().get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". Error: {err}'
            logger.error(details)

            result = DeleteConnectionResultFailure()
            return result

        # CURRENT RESTRICTION: Now vet the parents are in the same Flow (yes this sucks)
        if target_flow_name != source_flow_name:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". They are in different Flows (TEMPORARY RESTRICTION).'
            logger.error(details)

            result = DeleteConnectionResultFailure()
            return result

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" Not found.'
            logger.error(details)

            result = DeleteConnectionResultFailure()
            return result

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            details = f'Connection not deleted "{request.target_node_name}.{request.target_parameter_name}" Not found.'
            logger.error(details)

            result = DeleteConnectionResultFailure()
            return result

        # Vet that a Connection actually exists between them already.
        if not source_flow.has_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection does not exist: "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}"'
            logger.error(details)

            result = DeleteConnectionResultFailure()
            return result

        # Remove the connection.
        if not source_flow.remove_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection not deleted "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}". Unknown failure.'
            logger.error(details)

            result = DeleteConnectionResultFailure()
            return result

        # After the connection has been removed, if it doesn't have PROPERTY as a type, wipe the set parameter value and unresolve future nodes
        if ParameterMode.PROPERTY not in target_param.allowed_modes:
            try:
                target_node.remove_parameter_value(target_param.name)
                # It removed it accurately
                # Unresolve future nodes that depended on that value
                source_flow.connections.unresolve_future_nodes(target_node)
                target_node.make_node_unresolved()
            except KeyError as e:
                logger.warning(e)

        # Let the source make any internal handling decisions now that the Connection has been REMOVED.
        source_node.after_outgoing_connection_removed(
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        )

        # And target.
        target_node.after_incoming_connection_removed(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        )

        details = f'Connection "{request.source_node_name}.{request.source_parameter_name}" to "{request.target_node_name}.{request.target_parameter_name}" deleted.'
        logger.debug(details)

        result = DeleteConnectionResultSuccess()
        return result

    def on_start_flow_request(self, request: StartFlowRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912
        # which flow
        flow_name = request.flow_name
        debug_mode = request.debug_mode
        if not flow_name:
            details = "Must provide flow name to start a flow."
            logger.error(details)

            return StartFlowResultFailure(validation_exceptions=[])
        # get the flow by ID
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Cannot start flow. Error: {err}"
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[err])
        # A node has been provided to either start or to run up to.
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = GriptapeNodes.get_instance()._object_manager.attempt_get_object_by_name_as_type(
                flow_node_name, BaseNode
            )
            if not flow_node:
                details = f"Provided node with name {flow_node_name} does not exist"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[])
            # lets get the first control node in the flow!
            start_node = flow.get_start_node_from_node(flow_node)
            # if the start is not the node provided, set a breakpoint at the stop (we're running up until there)
            if not start_node:
                details = f"Start node for node with name {flow_node_name} does not exist"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[])
            if start_node != flow_node:
                flow_node.stop_flow = True
        else:
            # we wont hit this if we dont have a request id, our requests always have nodes
            # If there is a request, reinitialize the queue
            flow.get_start_node_queue()  # initialize the start flow queue!
            start_node = None
        # Run Validation before starting a flow
        result = self.on_validate_flow_dependencies_request(
            ValidateFlowDependenciesRequest(flow_name=flow_name, flow_node_name=start_node.name if start_node else None)
        )
        try:
            if not result.succeeded():
                details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[])
            result = cast("ValidateFlowDependenciesResultSuccess", result)

            if not result.validation_succeeded:
                details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed."
                if len(result.exceptions) > 0:
                    for exception in result.exceptions:
                        details = f"{details}\n\t{exception}"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=result.exceptions)
        except Exception as e:
            details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed: {e}"
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[e])
        # By now, it has been validated with no exceptions.
        try:
            flow.start_flow(flow_name, start_node, debug_mode)
        except Exception as e:
            details = f"Failed to kick off flow with name {flow_name}. Exception occurred: {e} "
            logger.error(details)
            if flow.check_for_existing_running_flow():
                # Cancel the flow run.
                cancel_request = CancelFlowRequest(flow_name=flow_name)
                GriptapeNodes.handle_request(cancel_request)

            return StartFlowResultFailure(validation_exceptions=[e])

        details = f"Successfully kicked off flow with name {flow_name}"
        logger.debug(details)

        return StartFlowResultSuccess()

    def on_get_flow_state_request(self, event: GetFlowStateRequest) -> ResultPayload:
        flow_name = event.flow_name
        if not flow_name:
            details = "Could not get flow state. No flow name was provided."
            logger.error(details)
            return GetFlowStateResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not get flow state. Error: {err}"
            logger.error(details)
            return GetFlowStateResultFailure()
        try:
            control_node, resolving_node = flow.flow_state()
        except Exception as e:
            details = f"Failed to get flow state of flow with name {flow_name}. Exception occurred: {e} "
            logger.error(details)
            return GetFlowStateResultFailure()
        details = f"Successfully got flow state for flow with name {flow_name}."
        logger.debug(details)
        return GetFlowStateResultSuccess(control_node=control_node, resolving_node=resolving_node)

    def on_cancel_flow_request(self, request: CancelFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not cancel flow execution. No flow name was provided."
            logger.error(details)

            return CancelFlowResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not cancel flow execution. Error: {err}"
            logger.error(details)

            return CancelFlowResultFailure()
        try:
            flow.cancel_flow_run()
        except Exception as e:
            details = f"Could not cancel flow execution. Exception: {e}"
            logger.error(details)

            return CancelFlowResultFailure()
        details = f"Successfully cancelled flow execution with name {flow_name}"
        logger.debug(details)

        return CancelFlowResultSuccess()

    def on_single_node_step_request(self, request: SingleNodeStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not step flow. No flow name was provided."
            logger.error(details)

            return SingleNodeStepResultFailure(validation_exceptions=[])
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not step flow. No flow with name {flow_name} exists. Error: {err}"
            logger.error(details)

            return SingleNodeStepResultFailure(validation_exceptions=[err])
        try:
            flow.single_node_step()
        except Exception as e:
            details = f"Could not step flow. Exception: {e}"
            logger.error(details)
            if flow.check_for_existing_running_flow():
                cancel_request = CancelFlowRequest(flow_name=flow_name)
                GriptapeNodes.handle_request(cancel_request)
            return SingleNodeStepResultFailure(validation_exceptions=[])

        # All completed happily
        details = f"Successfully stepped flow with name {flow_name}"
        logger.debug(details)

        return SingleNodeStepResultSuccess()

    def on_single_execution_step_request(self, request: SingleExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not single step flow. No flow name was provided."
            logger.error(details)

            return SingleExecutionStepResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not single step flow. Error: {err}."
            logger.error(details)

            return SingleExecutionStepResultFailure()
        try:
            flow.single_execution_step()
        except Exception as e:
            details = f"Could not step flow. Exception: {e}"
            logger.error(details)
            if flow.check_for_existing_running_flow():
                cancel_request = CancelFlowRequest(flow_name=flow_name)
                GriptapeNodes.handle_request(cancel_request)
            return SingleNodeStepResultFailure(validation_exceptions=[])
        details = f"Successfully granularly stepped flow with name {flow_name}"
        logger.debug(details)

        return SingleExecutionStepResultSuccess()

    def on_continue_execution_step_request(self, request: ContinueExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to continue execution step because no flow name was provided"
            logger.error(details)

            return ContinueExecutionStepResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to continue execution step. Error: {err}"
            logger.error(details)

            return ContinueExecutionStepResultFailure()
        try:
            flow.continue_executing()
        except Exception as e:
            details = f"Failed to continue execution step. An exception occurred: {e}."
            logger.error(details)
            if flow.check_for_existing_running_flow():
                cancel_request = CancelFlowRequest(flow_name=flow_name)
                GriptapeNodes.handle_request(cancel_request)
            return ContinueExecutionStepResultFailure()
        details = f"Successfully continued flow with name {flow_name}"
        logger.debug(details)
        return ContinueExecutionStepResultSuccess()

    def on_unresolve_flow_request(self, request: UnresolveFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to unresolve flow because no flow name was provided"
            logger.error(details)
            return UnresolveFlowResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to unresolve flow. Error: {err}"
            logger.error(details)
            return UnresolveFlowResultFailure()
        try:
            flow.unresolve_whole_flow()
        except Exception as e:
            details = f"Failed to unresolve flow. An exception occurred: {e}."
            logger.error(details)
            return UnresolveFlowResultFailure()
        details = f"Unresolved flow with name {flow_name}"
        logger.debug(details)
        return UnresolveFlowResultSuccess()

    def on_validate_flow_dependencies_request(self, request: ValidateFlowDependenciesRequest) -> ResultPayload:
        flow_name = request.flow_name
        # get the flow name
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to validate flow. Error: {err}"
            logger.error(details)
            return ValidateFlowDependenciesResultFailure()
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = GriptapeNodes.get_instance()._object_manager.attempt_get_object_by_name_as_type(
                flow_node_name, BaseNode
            )
            if not flow_node:
                details = f"Provided node with name {flow_node_name} does not exist"
                logger.error(details)
                return ValidateFlowDependenciesResultFailure()
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
        return ValidateFlowDependenciesResultSuccess(
            validation_succeeded=len(all_exceptions) == 0, exceptions=all_exceptions
        )

    def on_list_flows_in_current_context_request(self, request: ListFlowsInCurrentContextRequest) -> ResultPayload:  # noqa: ARG002 (request isn't actually used)
        if not GriptapeNodes.ContextManager().has_current_flow():
            details = "Attempted to list Flows in the Current Context. Failed because the Current Context was empty."
            logger.error(details)
            return ListFlowsInCurrentContextResultFailure()

        parent_flow_name = GriptapeNodes.ContextManager().get_current_flow_name()

        # Create a list of all child flow names that point DIRECTLY to us.
        ret_list = []
        for flow_name, parent_name in self._name_to_parent_name.items():
            if parent_name == parent_flow_name:
                ret_list.append(flow_name)

        details = f"Successfully got the list of Flows in the Current Context (Flow '{parent_flow_name}')."
        logger.debug(details)

        return ListFlowsInCurrentContextResultSuccess(flow_names=ret_list)


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
        event_manager.assign_manager_to_request_type(
            GetCompatibleParametersRequest, self.on_get_compatible_parameters_request
        )
        event_manager.assign_manager_to_request_type(
            ValidateNodeDependenciesRequest, self.on_validate_node_dependencies_request
        )
        event_manager.assign_manager_to_request_type(
            GetNodeElementDetailsRequest, self.on_get_node_element_details_request
        )

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
            # Try to get the current context flow
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = (
                    "Attempted to create Node in the Current Context. Failed because the Current Context was empty."
                )
                logger.error(details)
                return CreateNodeResultFailure()
            parent_flow_name = GriptapeNodes.ContextManager().get_current_flow_name()

        # Does this flow actually exist?
        flow_mgr = GriptapeNodes.FlowManager()
        try:
            flow = flow_mgr.get_flow_by_name(parent_flow_name)
        except KeyError as err:
            details = f"Could not create Node of type '{request.node_type}'. Error: {err}"
            logger.error(details)
            return CreateNodeResultFailure()

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
        # modifying to exception to try to catch all possible issues with node creation.
        except Exception as err:
            import traceback

            traceback.print_exc()
            details = f"Could not create Node '{final_node_name}' of type '{request.node_type}': {err}"
            logger.error(details)
            return CreateNodeResultFailure()

        # Add it to the Flow.
        flow.add_node(node)

        # Record keeping.
        obj_mgr.add_object_by_name(node.name, node)
        self._name_to_parent_flow_name[node.name] = parent_flow_name

        node.state = NodeResolutionState(request.resolution)

        # Success message based on whether we used Current Context or explicit flow
        if request.override_parent_flow_name is None:
            details = (
                f"Successfully created Node '{final_node_name}' in the Current Context (Flow '{parent_flow_name}')"
            )
        else:
            details = f"Successfully created Node '{final_node_name}' in Flow '{parent_flow_name}'"

        log_level = logging.DEBUG
        if remapped_requested_node_name:
            log_level = logging.WARNING
            details = f"{details}. WARNING: Had to rename from original node name requested '{request.node_name}' as an object with this name already existed."

        logger.log(level=log_level, msg=details)

        return CreateNodeResultSuccess(node_name=node.name)

    def on_delete_node_request(self, request: DeleteNodeRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to delete a Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = DeleteNodeResultFailure()
            return result

        parent_flow_name = self._name_to_parent_flow_name[request.node_name]
        try:
            parent_flow = GriptapeNodes().FlowManager().get_flow_by_name(parent_flow_name)
        except KeyError as err:
            details = f"Attempted to delete a Node '{request.node_name}'. Error: {err}"
            logger.error(details)

            result = DeleteNodeResultFailure()
            return result

        # Remove all connections from this Node.
        list_node_connections_request = ListConnectionsForNodeRequest(node_name=request.node_name)
        list_connections_result = GriptapeNodes().handle_request(request=list_node_connections_request)
        if isinstance(list_connections_result, ResultPayloadFailure):
            details = f"Attempted to delete a Node '{request.node_name}'. Failed because it could not gather Connections to the Node."
            logger.error(details)

            result = DeleteNodeResultFailure()
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
            if isinstance(delete_result, ResultPayloadFailure):
                details = (
                    f"Attempted to delete a Node '{request.node_name}'. Failed when attempting to delete Connection."
                )
                logger.error(details)

                result = DeleteNodeResultFailure()
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
            if isinstance(delete_result, ResultPayloadFailure):
                details = (
                    f"Attempted to delete a Node '{request.node_name}'. Failed when attempting to delete Connection."
                )
                logger.error(details)

                result = DeleteNodeResultFailure()
                return result

        # Remove from the owning Flow
        parent_flow.remove_node(node.name)

        # Now remove the record keeping
        obj_mgr.del_obj_by_name(request.node_name)
        del self._name_to_parent_flow_name[request.node_name]

        details = f"Successfully deleted Node '{request.node_name}'."
        logger.debug(details)

        result = DeleteNodeResultSuccess()
        return result

    def on_get_node_resolution_state_request(self, event: GetNodeResolutionStateRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(event.node_name, BaseNode)
        if node is None:
            details = f"Attempted to get resolution state for a Node '{event.node_name}', but no such Node was found."
            logger.error(details)
            result = GetNodeResolutionStateResultFailure()
            return result

        node_state = node.state

        details = f"Successfully got resolution state for Node '{event.node_name}'."
        logger.debug(details)

        result = GetNodeResolutionStateResultSuccess(
            state=node_state.name,
        )
        return result

    def on_get_node_metadata_request(self, request: GetNodeMetadataRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to get metadata for a Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = GetNodeMetadataResultFailure()
            return result

        metadata = node.metadata
        details = f"Successfully retrieved metadata for a Node '{request.node_name}'."
        logger.debug(details)

        result = GetNodeMetadataResultSuccess(
            metadata=metadata,
        )
        return result

    def on_set_node_metadata_request(self, request: SetNodeMetadataRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to set metadata for a Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = SetNodeMetadataResultFailure()
            return result
        # We can't completely overwrite metadata.
        for key, value in request.metadata.items():
            node.metadata[key] = value
        details = f"Successfully set metadata for a Node '{request.node_name}'."
        logger.debug(details)

        result = SetNodeMetadataResultSuccess()
        return result

    def on_list_connections_for_node_request(self, request: ListConnectionsForNodeRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to list Connections for a Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = ListConnectionsForNodeResultFailure()
            return result

        parent_flow_name = self._name_to_parent_flow_name[request.node_name]
        try:
            parent_flow = GriptapeNodes().FlowManager().get_flow_by_name(parent_flow_name)
        except KeyError as err:
            details = f"Attempted to list Connections for a Node '{request.node_name}'. Error: {err}"
            logger.error(details)

            result = ListConnectionsForNodeResultFailure()
            return result

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
        logger.debug(details)

        result = ListConnectionsForNodeResultSuccess(
            incoming_connections=incoming_connections_list,
            outgoing_connections=outgoing_connections_list,
        )
        return result

    def on_list_parameters_on_node_request(self, request: ListParametersOnNodeRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to list Parameters for a Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = ListParametersOnNodeResultFailure()
            return result

        ret_list = [param.name for param in node.parameters]

        details = f"Successfully listed Parameters for Node '{request.node_name}'."
        logger.debug(details)

        result = ListParametersOnNodeResultSuccess(
            parameter_names=ret_list,
        )
        return result

    def on_add_parameter_to_node_request(self, request: AddParameterToNodeRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to add Parameter '{request.parameter_name}' to a Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = AddParameterToNodeResultFailure()
            return result

        if request.parent_container_name and not request.initial_setup:
            parameter = node.get_parameter_by_name(request.parent_container_name)
            if parameter is None:
                details = f"Attempted to add Parameter to Container Parameter '{request.parent_container_name}' in node '{request.node_name}'. Failed because parameter didn't exist."
                logger.error(details)
                result = AddParameterToNodeResultFailure()
                return result
            if not isinstance(parameter, ParameterContainer):
                details = f"Attempted to add Parameter to Container Parameter '{request.parent_container_name}' in node '{request.node_name}'. Failed because parameter wasn't a container."
                logger.error(details)
                result = AddParameterToNodeResultFailure()
                return result
            try:
                new_param = parameter.add_child_parameter()
            except Exception as e:
                details = f"Attempted to add Parameter to Container Parameter '{request.parent_container_name}' in node '{request.node_name}'. Failed: {e}."
                logger.exception(details)
                result = AddParameterToNodeResultFailure()
                return result
            return AddParameterToNodeResultSuccess(
                parameter_name=new_param.name, type=new_param.type, node_name=request.node_name
            )
        if request.parameter_name is None or request.tooltip is None:
            details = f"Attempted to add Parameter to node '{request.node_name}'. Failed because default_value, tooltip, or parameter_name was not defined."
            logger.error(details)
            result = AddParameterToNodeResultFailure()
            return result
        # Does the Node already have a parameter by this name?
        if node.get_parameter_by_name(request.parameter_name) is not None:
            details = f"Attempted to add Parameter '{request.parameter_name}' to Node '{request.node_name}'. Failed because it already had a Parameter with that name on it. Parameter names must be unique within the Node."
            logger.error(details)

            result = AddParameterToNodeResultFailure()
            return result

        # Let's see if the Parameter is properly formed.
        # If a Parameter is intended for Control, it needs to have that be the exclusive type.
        # The 'type', 'types', and 'output_type' are a little weird to handle (see Parameter definition for details)
        has_control_type = False
        has_non_control_types = False
        if request.type is not None:
            if request.type.lower() == ParameterTypeBuiltin.CONTROL_TYPE.value.lower():
                has_control_type = True
            else:
                has_non_control_types = True
        if request.input_types is not None:
            for test_type in request.input_types:
                if test_type.lower == ParameterTypeBuiltin.CONTROL_TYPE.value.lower():
                    has_control_type = True
                else:
                    has_non_control_types = True
        if request.output_type is not None:
            if request.output_type.lower() == ParameterTypeBuiltin.CONTROL_TYPE.value.lower():
                has_control_type = True
            else:
                has_non_control_types = True

        if has_control_type and has_non_control_types:
            details = f"Attempted to add Parameter '{request.parameter_name}' to Node '{request.node_name}'. Failed because it had 'ParameterControlType' AND at least one other non-control type. If a Parameter is intended for control, it must only accept that type."
            logger.error(details)

            result = AddParameterToNodeResultFailure()
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
            type=request.type,
            input_types=request.input_types,
            output_type=request.output_type,
            default_value=request.default_value,
            user_defined=True,
            tooltip=request.tooltip,
            tooltip_as_input=request.tooltip_as_input,
            tooltip_as_property=request.tooltip_as_property,
            tooltip_as_output=request.tooltip_as_output,
            allowed_modes=allowed_modes,
            ui_options=request.ui_options,
            parent_container_name=request.parent_container_name,
        )
        try:
            if request.parent_container_name and request.initial_setup:
                parameter_parent = node.get_parameter_by_name(request.parent_container_name)
                if parameter_parent is not None:
                    parameter_parent.add_child(new_param)
            else:
                logger.info(new_param.name)
                node.add_parameter(new_param)
        except Exception as e:
            details = f"Couldn't add parameter with name {request.parameter_name} to node. Error: {e}"
            logger.error(details)
            return AddParameterToNodeResultFailure()

        details = f"Successfully added Parameter '{request.parameter_name}' to Node '{request.node_name}'."
        logger.debug(details)

        result = AddParameterToNodeResultSuccess(
            parameter_name=new_param.name, type=new_param.type, node_name=request.node_name
        )
        return result

    def on_remove_parameter_from_node_request(self, request: RemoveParameterFromNodeRequest) -> ResultPayload:  # noqa: C901
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from a Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = RemoveParameterFromNodeResultFailure()
            return result

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(request.parameter_name)
        parameter_group = node.get_group_by_name_or_element_id(request.parameter_name)
        if parameter is None and parameter_group is None:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because it didn't have a Parameter with that name on it."
            logger.error(details)

            result = RemoveParameterFromNodeResultFailure()
            return result
        if parameter_group is not None:
            for child in parameter_group.find_elements_by_type(Parameter):
                GriptapeNodes.handle_request(RemoveParameterFromNodeRequest(child.name, request.node_name))
            node.remove_group_by_name(request.parameter_name)
            return RemoveParameterFromNodeResultSuccess()

        # No tricky stuff, users!
        if parameter.user_defined is False:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because the Parameter was not user-defined (i.e., critical to the Node implementation). Only user-defined Parameters can be removed from a Node."
            logger.error(details)

            result = RemoveParameterFromNodeResultFailure()
            return result

        # Get all the connections to/from this Parameter.
        list_node_connections_request = ListConnectionsForNodeRequest(node_name=request.node_name)
        list_connections_result = GriptapeNodes().handle_request(request=list_node_connections_request)
        if isinstance(list_connections_result, ListConnectionsForNodeResultFailure):
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because we were unable to get a list of Connections for the Parameter's Node."
            logger.error(details)

            result = RemoveParameterFromNodeResultFailure()
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
                if isinstance(delete_result, DeleteConnectionResultFailure):
                    details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because we were unable to delete a Connection for that Parameter."
                    logger.error(details)

                    result = RemoveParameterFromNodeResultFailure()

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
                if isinstance(delete_result, DeleteConnectionResultFailure):
                    details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because we were unable to delete a Connection for that Parameter."
                    logger.error(details)

                    result = RemoveParameterFromNodeResultFailure()

        # Delete the Parameter itself.
        node.remove_parameter(parameter)

        details = f"Successfully removed Parameter '{request.parameter_name}' from Node '{request.node_name}'."
        logger.debug(details)

        result = RemoveParameterFromNodeResultSuccess()
        return result

    def on_get_parameter_details_request(self, request: GetParameterDetailsRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to get details for Parameter '{request.parameter_name}' from a Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = GetParameterDetailsResultFailure()
            return result

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(request.parameter_name)
        if parameter is None:
            details = f"Attempted to get details for Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because it didn't have a Parameter with that name on it."
            logger.error(details)

            result = GetParameterDetailsResultFailure()
            return result

        # Let's bundle up the details.
        modes_allowed = parameter.allowed_modes
        allows_input = ParameterMode.INPUT in modes_allowed
        allows_property = ParameterMode.PROPERTY in modes_allowed
        allows_output = ParameterMode.OUTPUT in modes_allowed

        details = f"Successfully got details for Parameter '{request.parameter_name}' from Node '{request.node_name}'."
        logger.debug(details)

        result = GetParameterDetailsResultSuccess(
            element_id=parameter.element_id,
            type=parameter.type,
            input_types=parameter.input_types,
            output_type=parameter.output_type,
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

    def on_get_node_element_details_request(self, request: GetNodeElementDetailsRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to get element details for Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = GetNodeElementDetailsResultFailure()
            return result

        # Did they ask for a specific element ID?
        if request.specific_element_id is None:
            # No? Use the node's root element to search from.
            element = node.root_ui_element
        else:
            element = node.findroot_ui_element.find_element_by_id(request.specific_element_id)
            if element is None:
                details = f"Attempted to get element details for element '{request.specific_element_id}' from Node '{request.node_name}'. Failed because it didn't have an element with that ID on it."
                logger.error(details)

                result = GetNodeElementDetailsResultFailure()
                return result

        element_details = element.to_dict()
        # We need to get parameter values from here
        param_to_value = {}
        self._set_param_to_value(node, element, param_to_value)
        if param_to_value:
            element_details["element_id_to_value"] = param_to_value
        details = f"Successfully got element details for Node '{request.node_name}'."
        logger.debug(details)
        result = GetNodeElementDetailsResultSuccess(element_details=element_details)
        return result

    def _set_param_to_value(self, node: BaseNode, element: BaseNodeElement, param_to_value: dict) -> None:
        """This method builds our element_id_to_value mapping to eventually return in the Element Details Request."""
        # Get all parameters
        for parameter in element.find_elements_by_type(Parameter):
            # Check if they have an output value, that takes priority
            if parameter.name in node.parameter_output_values:
                value = node.parameter_output_values[parameter.name]
            else:
                # Otherwise grab the set value or default value
                value = node.get_parameter_value(parameter.name)
            if value is not None:
                element_id = parameter.element_id
                # Check if the value is in builtins. If it isn't we need to handle it specially.
                if value.__class__.__module__ != "builtins":
                    # Check if it has a to_dict method. Use that, if it's been implemented.
                    if hasattr(value, "to_dict"):
                        # If the object has a __dict__, use that
                        param_to_value[element_id] = value.to_dict()
                        return
                    # Otherwise use __dict__.
                    if hasattr(value, "__dict__"):
                        param_to_value[element_id] = value.__dict__
                        return
                # Otherwise, just set it here. It'll be handled in .json() when we send it over.
                param_to_value[element_id] = value

    def modify_alterable_fields(self, request: AlterParameterDetailsRequest, parameter: Parameter) -> None:
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

    def modify_key_parameter_fields(self, request: AlterParameterDetailsRequest, parameter: Parameter) -> None:
        if request.type is not None:
            parameter.type = request.type
        if request.input_types is not None:
            parameter.input_types = request.input_types
        if request.output_type is not None:
            parameter.output_type = request.output_type
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

    def on_alter_parameter_details_request(self, request: AlterParameterDetailsRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to alter details for Parameter '{request.parameter_name}' from Node '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = AlterParameterDetailsResultFailure()
            return result

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(request.parameter_name)
        parameter_group = node.get_group_by_name_or_element_id(request.parameter_name)
        if parameter is None:
            parameter_group = node.get_group_by_name_or_element_id(request.parameter_name)
            if parameter_group is None:
                details = f"Attempted to alter details for Parameter '{request.parameter_name}' from Node '{request.node_name}'. Failed because it didn't have a Parameter with that name on it."
                logger.error(details)

                result = AlterParameterDetailsResultFailure()
                return result
            if request.ui_options is not None:
                parameter_group.ui_options = request.ui_options
            return AlterParameterDetailsResultSuccess()

        # TODO(griptape): Verify that we can get through all the OTHER tricky stuff before we proceed to actually making changes.
        # Now change all the values on the Parameter.
        self.modify_alterable_fields(request, parameter)
        # The rest of these are not alterable
        if parameter.user_defined is False and request.request_id:
            # TODO(griptape): there may be SOME properties on a non-user-defined Parameter that can be changed
            details = f"Attempted to alter details for Parameter '{request.parameter_name}' from Node '{request.node_name}'. Could only alter some values because the Parameter was not user-defined (i.e., critical to the Node implementation). Only user-defined Parameters can be totally modified from a Node."
            logger.warning(details)
            result = AlterParameterDetailsResultSuccess()
            return result
        self.modify_key_parameter_fields(request, parameter)
        # This field requires the node as well
        if request.default_value is not None:
            # TODO(griptape): vet that default value matches types allowed
            node.parameter_values[request.parameter_name] = request.default_value

        details = (
            f"Successfully altered details for Parameter '{request.parameter_name}' from Node '{request.node_name}'."
        )
        logger.debug(details)

        result = AlterParameterDetailsResultSuccess()
        return result

    # For C901 (too complex): Need to give customers explicit reasons for failure on each case.
    def on_get_parameter_value_request(self, request: GetParameterValueRequest) -> ResultPayload:
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        # Parse the parameter name to check for list indexing
        param_name = request.parameter_name

        # Get the node
        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f'"{request.node_name}" not found'
            logger.error(details)
            return GetParameterValueResultFailure()

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(param_name)
        if parameter is None:
            details = f'"{request.node_name}.{param_name}" not found'
            logger.error(details)
            return GetParameterValueResultFailure()

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

        # Cool.
        details = f"{request.node_name}.{request.parameter_name} = {data_value}"
        logger.debug(details)

        result = GetParameterValueResultSuccess(
            input_types=parameter.input_types,
            type=parameter.type,
            output_type=parameter.output_type,
            value=TypeValidator.safe_serialize(data_value),
        )
        return result

    # added ignoring C901 since this method is overly long because of granular error checking, not actual complexity.
    def on_set_parameter_value_request(self, request: SetParameterValueRequest) -> ResultPayload:  # noqa: C901, PLR0911
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        # Parse the parameter name to check for list indexing
        param_name = request.parameter_name

        # Get the node
        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to set parameter '{param_name}' value on node '{request.node_name}'. Failed because no such Node could be found."
            logger.error(details)
            return SetParameterValueResultFailure()

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(param_name)
        if parameter is None:
            details = f"Attempted to set parameter value for '{request.node_name}.{param_name}'. Failed because no parameter with that name could be found."
            logger.error(details)

            result = SetParameterValueResultFailure()
            return result

        # Validate that parameters can be set at all
        if not parameter.settable:
            details = f"Attempted to set parameter value for '{request.node_name}.{request.parameter_name}'. Failed because that Parameter was flagged as not settable."
            logger.error(details)
            result = SetParameterValueResultFailure()
            return result

        # Well this seems kind of stupid
        object_type = request.data_type if request.data_type else parameter.type
        # Is this value kosher for the types allowed?
        if not parameter.is_incoming_type_allowed(object_type):
            details = f"Attempted to set parameter value for '{request.node_name}.{request.parameter_name}'. Failed because the value's type of '{object_type}' was not in the Parameter's list of allowed types: {parameter.input_types}."
            logger.error(details)

            result = SetParameterValueResultFailure()
            return result

        try:
            parent_flow_name = self.get_node_parent_flow_by_name(node.name)
        except KeyError:
            details = f"Attempted to set parameter value for '{request.node_name}.{request.parameter_name}'. Failed because the node's parent flow does not exist. Could not unresolve future nodes."
            logger.error(details)
            return SetParameterValueResultFailure()
        parent_flow = obj_mgr.attempt_get_object_by_name_as_type(parent_flow_name, ControlFlow)
        if not parent_flow:
            details = f"Attempted to set parameter value for '{request.node_name}.{request.parameter_name}'. Failed because the node's parent flow does not exist. Could not unresolve future nodes."
            logger.error(details)
            return SetParameterValueResultFailure()
        try:
            parent_flow.connections.unresolve_future_nodes(node)
        except Exception as err:
            details = f"Attempted to set parameter value for '{request.node_name}.{request.parameter_name}'. Failed because Exception: {err}"
            logger.error(details)
            return SetParameterValueResultFailure()

        # Values are actually stored on the NODE.
        try:
            finalized_value = self._set_and_pass_through_values(request, node)
        except Exception as err:
            details = f"Attempted to set parameter value for '{request.node_name}.{request.parameter_name}'. Failed because Exception: {err}"
            logger.error(details)
            return SetParameterValueResultFailure()
        # Mark node as unresolved
        if request.initial_setup is False and not request.is_output:
            node.state = NodeResolutionState.UNRESOLVED
            # Get the flow
            # Pass the value through!
            # Optional data_type parameter for internal handling!
            conn_output_nodes = parent_flow.get_connected_output_parameters(node, parameter)
            for target_node, target_parameter in conn_output_nodes:
                GriptapeNodes.get_instance().handle_request(
                    SetParameterValueRequest(
                        parameter_name=target_parameter.name,
                        node_name=target_node.name,
                        value=finalized_value,
                        data_type=object_type,  # Do type instead of output type, because it hasn't been processed.
                    )
                )

        # Cool.
        details = f"Successfully set value on Node '{request.node_name}' Parameter '{request.parameter_name}'."
        logger.debug(details)

        result = SetParameterValueResultSuccess(finalized_value=finalized_value, data_type=parameter.type)
        return result

    def _set_and_pass_through_values(self, request: SetParameterValueRequest, node: BaseNode) -> Any:
        """Set the parameter value on the node according to the specifications."""
        object_created = request.value
        # If the value should be set on the output dictionary:
        if request.is_output:
            # set it to output values
            node.parameter_output_values[request.parameter_name] = object_created
            return object_created
        # Otherwise use set_parameter_value. This calls our converters and validators.
        modified_parameters = node.set_parameter_value(request.parameter_name, object_created)
        # Get the "converted" value here.
        finalized_value = node.get_parameter_value(request.parameter_name)
        # If any parameters were dependent on that value, we're calling this details request to emit the result to the editor.
        if modified_parameters:
            for modified_parameter_name in modified_parameters:
                modified_request = GetParameterDetailsRequest(
                    parameter_name=modified_parameter_name, node_name=node.name
                )
                GriptapeNodes.handle_request(modified_request)
        return finalized_value

    # For C901 (too complex): Need to give customers explicit reasons for failure on each case.
    # For PLR0911 (too many return statements): don't want to do a ton of nested chains of success,
    # want to give clear reasoning for each failure.
    # For PLR0915 (too many statements): very little reusable code here, want to be explicit and
    # make debugger use friendly.
    def on_get_all_node_info_request(self, request: GetAllNodeInfoRequest) -> ResultPayload:  # noqa: PLR0911, PLR0915
        # Does this node exist?
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(request.node_name, BaseNode)
        if node is None:
            details = f"Attempted to get all info for Node named '{request.node_name}', but no such Node was found."
            logger.error(details)

            result = GetAllNodeInfoResultFailure()
            return result

        get_metadata_request = GetNodeMetadataRequest(node_name=request.node_name)
        get_metadata_result = GriptapeNodes.NodeManager().on_get_node_metadata_request(get_metadata_request)
        if not get_metadata_result.succeeded():
            details = (
                f"Attempted to get all info for Node named '{request.node_name}', but failed getting the metadata."
            )
            logger.error(details)

            result = GetAllNodeInfoResultFailure()
            return result

        get_resolution_state_request = GetNodeResolutionStateRequest(node_name=request.node_name)
        get_resolution_state_result = GriptapeNodes.NodeManager().on_get_node_resolution_state_request(
            get_resolution_state_request
        )
        if not get_resolution_state_result.succeeded():
            details = f"Attempted to get all info for Node named '{request.node_name}', but failed getting the resolution state."
            logger.error(details)

            result = GetAllNodeInfoResultFailure()
            return result

        list_connections_request = ListConnectionsForNodeRequest(node_name=request.node_name)
        list_connections_result = GriptapeNodes.NodeManager().on_list_connections_for_node_request(
            list_connections_request
        )
        if not list_connections_result.succeeded():
            details = f"Attempted to get all info for Node named '{request.node_name}', but failed listing all connections for it."
            logger.error(details)

            result = GetAllNodeInfoResultFailure()
            return result
        # Cast everything to get the linter off our back.
        try:
            get_metadata_success = cast("GetNodeMetadataResultSuccess", get_metadata_result)
            get_resolution_state_success = cast("GetNodeResolutionStateResultSuccess", get_resolution_state_result)
            list_connections_success = cast("ListConnectionsForNodeResultSuccess", list_connections_result)
        except Exception as err:
            details = f"Attempted to get all info for Node named '{request.node_name}'. Failed due to error: {err}."
            logger.error(details)

            result = GetAllNodeInfoResultFailure()
            return result
        get_node_elements_request = GetNodeElementDetailsRequest(node_name=request.node_name)
        get_node_elements_result = GriptapeNodes.NodeManager().on_get_node_element_details_request(
            get_node_elements_request
        )
        if not get_node_elements_result.succeeded():
            details = f"Attempted to get all info for Node named '{request.node_name}', but failed getting details for elements."
            logger.error(details)
            result = GetAllNodeInfoResultFailure()
            return result
        try:
            get_element_details_success = cast("GetNodeElementDetailsResultSuccess", get_node_elements_result)
        except Exception as err:
            details = f"Attempted to get all info for Node named '{request.node_name}'. Failed due to error: {err}."
            logger.exception(details)
            result = GetAllNodeInfoResultFailure()
            return result

        # this will return the node element and the value
        element_details = get_element_details_success.element_details
        if "element_id_to_value" in element_details:
            element_id_to_value = element_details["element_id_to_value"].copy()
            del element_details["element_id_to_value"]
        else:
            element_id_to_value = {}
        details = f"Successfully got all node info for node '{request.node_name}'."
        logger.debug(details)
        result = GetAllNodeInfoResultSuccess(
            metadata=get_metadata_success.metadata,
            node_resolution_state=get_resolution_state_success.state,
            connections=list_connections_success,
            element_id_to_value=element_id_to_value,
            root_node_element=element_details,
        )
        return result

    def on_get_compatible_parameters_request(self, request: GetCompatibleParametersRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915
        # Vet the node
        try:
            node = GriptapeNodes.NodeManager().get_node_by_name(request.node_name)
        except ValueError as err:
            details = f"Attempted to get compatible parameters for node '{request.node_name}', but that node does not exist. Error: {err}."
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Vet the parameter.
        request_param = node.get_parameter_by_name(request.parameter_name)
        if request_param is None:
            details = f"Attempted to get compatible parameters for '{request.node_name}.{request.parameter_name}', but that no Parameter with that name could not be found."
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Figure out the mode we're going for, and if this parameter supports the mode.
        request_mode = ParameterMode.OUTPUT if request.is_output else ParameterMode.INPUT
        # Does this parameter support that?
        if request_mode not in request_param.allowed_modes:
            details = f"Attempted to get compatible parameters for '{request.node_name}.{request.parameter_name}' as '{request_mode}', but the Parameter didn't support that type of input/output."
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Get the parent flows.
        try:
            flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(request.node_name)
        except KeyError as err:
            details = f"Attempted to get compatible parameters for '{request.node_name}.{request.parameter_name}', but the node's parent flow could not be found: {err}"
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Iterate through all nodes in this Flow (yes, this restriction still sucks)
        list_nodes_in_flow_request = ListNodesInFlowRequest(flow_name=flow_name)
        list_nodes_in_flow_result = GriptapeNodes.FlowManager().on_list_nodes_in_flow_request(
            list_nodes_in_flow_request
        )
        if not list_nodes_in_flow_result.succeeded():
            details = f"Attempted to get compatible parameters for '{request.node_name}.{request.parameter_name}'. Failed due to inability to list nodes in parent flow '{flow_name}'."
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        try:
            list_nodes_in_flow_success = cast("ListNodesInFlowResultSuccess", list_nodes_in_flow_result)
        except Exception as err:
            details = f"Attempted to get compatible parameters for '{request.node_name}.{request.parameter_name}'. Failed due to {err}"
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Walk through all nodes that are NOT us to find compatible Parameters.
        valid_parameters_by_node = {}
        for test_node_name in list_nodes_in_flow_success.node_names:
            if test_node_name != request.node_name:
                # Get node by name
                try:
                    test_node = GriptapeNodes.NodeManager().get_node_by_name(test_node_name)
                except ValueError as err:
                    details = f"Attempted to get compatible parameters for node '{request.node_name}', and sought to test against {test_node_name}, but that node does not exist. Error: {err}."
                    logger.error(details)
                    return GetCompatibleParametersResultFailure()

                # Get Parameters from Node
                for test_param in test_node.parameters:
                    # Are we compatible from an input/output perspective?
                    fits_mode = False
                    if request_mode == ParameterMode.INPUT:
                        fits_mode = ParameterMode.OUTPUT in test_param.allowed_modes
                    else:
                        fits_mode = ParameterMode.INPUT in test_param.allowed_modes

                    if fits_mode:
                        # Compare types for compatibility
                        types_compatible = False
                        if request_mode == ParameterMode.INPUT:
                            # See if THEIR inputs would accept MY output
                            types_compatible = test_param.is_incoming_type_allowed(request_param.output_type)
                        else:
                            # See if MY inputs would accept THEIR output
                            types_compatible = request_param.is_incoming_type_allowed(test_param.output_type)

                        if types_compatible:
                            param_and_mode = ParameterAndMode(
                                parameter_name=test_param.name, is_output=not request.is_output
                            )
                            # Add the test param to our dictionary.
                            if test_node_name in valid_parameters_by_node:
                                # Append this parameter to the list
                                compatible_list = valid_parameters_by_node[test_node_name]
                                compatible_list.append(param_and_mode)
                            else:
                                # Create new
                                compatible_list = [param_and_mode]
                                valid_parameters_by_node[test_node_name] = compatible_list

        details = f"Successfully got compatible parameters for '{request.node_name}.{request.parameter_name}'."
        logger.debug(details)
        return GetCompatibleParametersResultSuccess(valid_parameters_by_node=valid_parameters_by_node)

    def get_node_by_name(self, name: str) -> BaseNode:
        obj_mgr = GriptapeNodes().get_instance().ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(name, BaseNode)
        if node is None:
            msg = f"Node '{name}' not found."
            raise ValueError(msg)

        return node

    def get_node_parent_flow_by_name(self, node_name: str) -> str:
        if node_name not in self._name_to_parent_flow_name:
            msg = f"Node '{node_name}' could not be found."
            raise KeyError(msg)
        return self._name_to_parent_flow_name[node_name]

    def on_resolve_from_node_request(self, request: ResolveNodeRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0915, PLR0912
        node_name = request.node_name
        debug_mode = request.debug_mode

        if not node_name:
            details = "No Node name was provided. Failed to resolve node."
            logger.error(details)

            return ResolveNodeResultFailure(validation_exceptions=[])
        try:
            node = GriptapeNodes.NodeManager().get_node_by_name(node_name)
        except ValueError as e:
            details = f'Resolve failure. "{node_name}" does not exist. {e}'
            logger.error(details)

            return ResolveNodeResultFailure(validation_exceptions=[e])
        # try to get the flow parent of this node
        try:
            flow_name = self._name_to_parent_flow_name[node_name]
        except KeyError as e:
            details = f'Failed to fetch parent flow for "{node_name}": {e}'
            logger.error(details)

            return ResolveNodeResultFailure(validation_exceptions=[e])
        try:
            obj_mgr = GriptapeNodes()._object_manager
            flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        except KeyError as e:
            details = f'Failed to fetch parent flow for "{node_name}": {e}'
            logger.error(details)

            return ResolveNodeResultFailure(validation_exceptions=[e])

        if flow is None:
            details = f'Failed to fetch parent flow for "{node_name}"'
            logger.error(details)
            return ResolveNodeResultFailure(validation_exceptions=[])
        try:
            flow.connections.unresolve_future_nodes(node)
        except Exception as e:
            details = f'Failed to mark future nodes dirty. Unable to kick off flow from "{node_name}": {e}'
            logger.error(details)
            return ResolveNodeResultFailure(validation_exceptions=[e])
        # Validate here.
        result = self.on_validate_node_dependencies_request(ValidateNodeDependenciesRequest(node_name=node_name))
        try:
            if not result.succeeded():
                details = f"Failed to resolve node '{node_name}'. Flow Validation Failed"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[])
            result = cast("ValidateNodeDependenciesResultSuccess", result)

            if not result.validation_succeeded:
                details = f"Failed to resolve node '{node_name}'. Flow Validation Failed."
                if len(result.exceptions) > 0:
                    for exception in result.exceptions:
                        details = f"{details}\n\t{exception}"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=result.exceptions)
        except Exception as e:
            details = f"Failed to resolve node '{node_name}'. Flow Validation Failed. Error: {e}"
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[e])
        try:
            flow.resolve_singular_node(node, debug_mode)
        except Exception as e:
            details = f'Failed to resolve "{node_name}".  Error: {e}'
            logger.error(details)
            if flow.check_for_existing_running_flow():
                cancel_request = CancelFlowRequest(flow_name=flow_name)
                GriptapeNodes.handle_request(cancel_request)
            return ResolveNodeResultFailure(validation_exceptions=[e])
        details = f'Starting to resolve "{node_name}" in "{flow_name}"'
        logger.debug(details)
        return ResolveNodeResultSuccess()

    def on_validate_node_dependencies_request(self, request: ValidateNodeDependenciesRequest) -> ResultPayload:
        node_name = request.node_name
        obj_manager = GriptapeNodes.get_instance()._object_manager
        node = obj_manager.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if not node:
            details = f'Failed to validate node dependencies. Node with "{node_name}" does not exist.'
            logger.error(details)
            return ValidateNodeDependenciesResultFailure()
        try:
            flow_name = self.get_node_parent_flow_by_name(node_name)
        except Exception as e:
            details = f'Failed to validate node dependencies. Node with "{node_name}" has no parent flow. Error: {e}'
            logger.error(details)
            return ValidateNodeDependenciesResultFailure()
        flow = GriptapeNodes.get_instance()._object_manager.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if not flow:
            details = f'Failed to validate node dependencies. Flow with "{flow_name}" does not exist.'
            logger.error(details)
            return ValidateNodeDependenciesResultFailure()
        # Gets all dependent nodes
        nodes = flow.get_node_dependencies(node)
        all_exceptions = []
        for dependent_node in nodes:
            exceptions = dependent_node.validate_node()
            if exceptions:
                all_exceptions = all_exceptions + exceptions
        return ValidateNodeDependenciesResultSuccess(
            validation_succeeded=(len(all_exceptions) == 0), exceptions=all_exceptions
        )


class WorkflowManager:
    WORKFLOW_METADATA_HEADER: ClassVar[str] = "script"

    def __init__(self, event_manager: EventManager) -> None:
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

    def run_workflow(self, relative_file_path: str) -> tuple[bool, str]:
        relative_file_path_obj = Path(relative_file_path)
        if relative_file_path_obj.is_absolute():
            complete_file_path = relative_file_path_obj
        else:
            complete_file_path = WorkflowRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        try:
            # TODO(griptape): scope the libraries loaded to JUST those used by this workflow, eventually: https://github.com/griptape-ai/griptape-nodes/issues/284
            # Load (or reload, which should trigger a hot reload) all libraries
            GriptapeNodes.LibraryManager().load_all_libraries_from_config()

            # Now execute the workflow.
            with Path(complete_file_path).open() as file:
                workflow_content = file.read()
            exec(workflow_content)  # noqa: S102
        except Exception as e:
            return (
                False,
                f"Failed to run workflow on path '{complete_file_path}'. Exception: {e}",
            )
        return True, f"Succeeded in running workflow on path '{complete_file_path}'."

    def on_run_workflow_from_scratch_request(self, request: RunWorkflowFromScratchRequest) -> ResultPayload:
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
        success, details = self.run_workflow(relative_file_path=relative_file_path)
        if success:
            logger.debug(details)
            return RunWorkflowFromScratchResultSuccess()

        logger.error(details)
        return RunWorkflowFromScratchResultFailure()

    def on_run_workflow_with_current_state_request(self, request: RunWorkflowWithCurrentStateRequest) -> ResultPayload:
        relative_file_path = request.file_path
        complete_file_path = WorkflowRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        if not Path(complete_file_path).is_file():
            details = f"Failed to find file. Path '{complete_file_path}' doesn't exist."
            logger.error(details)
            return RunWorkflowWithCurrentStateResultFailure()
        success, details = self.run_workflow(relative_file_path=relative_file_path)

        if success:
            logger.debug(details)
            return RunWorkflowWithCurrentStateResultSuccess()
        logger.error(details)
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
                details = (
                    f"When preparing to run a workflow '{request.workflow_name}', failed to get registered libraries."
                )
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
        success, details = self.run_workflow(relative_file_path=relative_file_path)

        if success:
            logger.debug(details)
            return RunWorkflowFromRegistryResultSuccess()

        logger.error(details)
        return RunWorkflowFromRegistryResultFailure()

    def on_register_workflow_request(self, request: RegisterWorkflowRequest) -> ResultPayload:
        try:
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
        config_manager = GriptapeNodes.get_instance()._config_manager
        try:
            config_manager.delete_user_workflow(workflow.__dict__)
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

    def on_load_workflow_metadata_request(self, request: LoadWorkflowMetadata) -> ResultPayload:
        # Let us go into the darkness.
        complete_file_path = GriptapeNodes.ConfigManager().workspace_path.joinpath(request.file_name)
        if not Path(complete_file_path).is_file():
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}. Failed because no file could be found at that path."
            logger.error(details)
            return LoadWorkflowMetadataResultFailure()

        # Open 'er up.
        with complete_file_path.open("r") as file:
            workflow_content = file.read()

        # Find the metadata block.
        regex = r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"
        block_name = "script"
        matches = list(filter(lambda m: m.group("type") == block_name, re.finditer(regex, workflow_content)))
        if len(matches) != 1:
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
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed because the metadata was not valid TOML: {err}"
            logger.error(details)
            return LoadWorkflowMetadataResultFailure()

        try:
            griptape_nodes_tool_section = toml_doc["tool"]["griptape-nodes"]  # type: ignore (this is the only way I could find to get tomlkit to do the dotted notation correctly)
        except Exception as err:
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed because the '[tools.griptape-nodes]' section could not be found: {err}"
            logger.error(details)
            return LoadWorkflowMetadataResultFailure()

        try:
            # Is it kosher?
            workflow_metadata = WorkflowMetadata.model_validate(griptape_nodes_tool_section)
        except Exception as err:
            # No, it is haram.
            details = f"Attempted to load workflow metadata for a file at '{complete_file_path}'. Failed because the metadata did not match the requisite schema with error: {err}"
            logger.error(details)
            return LoadWorkflowMetadataResultFailure()

        return LoadWorkflowMetadataResultSuccess(metadata=workflow_metadata)

    def on_save_workflow_request(self, request: SaveWorkflowRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915 (need lots of branches to cover negative cases)
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
                    code_string = f"GriptapeNodes().handle_request({creation_request})"
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
            config_manager.save_user_workflow_json(relative_file_path)
            WorkflowRegistry.generate_new_workflow(metadata=workflow_metadata, file_path=relative_file_path)
        details = f"Successfully saved workflow to: {file_path}"
        logger.info(details)
        return SaveWorkflowResultSuccess(file_path=str(file_path))


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
            code_string = f"GriptapeNodes().handle_request({creation_request})"
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
            code_string = f"GriptapeNodes().handle_request({creation_request})\n"
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
                code_string = f"GriptapeNodes().handle_request({creation_request})\n"
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
            return f"GriptapeNodes().handle_request(SetParameterValueRequest(parameter_name='{parameter.name}', node_name='{node.name}', value={var_name}, initial_setup=True, is_output={is_output}))"
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
                + f"GriptapeNodes().handle_request(SetParameterValueRequest(parameter_name='{parameter.name}', node_name='{node.name}', value={var_name}, initial_setup=True, is_output={is_output}))"
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
        event_manager.assign_manager_to_request_type(
            UnloadLibraryFromRegistryRequest, self.unload_library_from_registry_request
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

    def register_library_from_file_request(self, request: RegisterLibraryFromFileRequest) -> ResultPayload:
        file_path = request.file_path

        # Convert to Path object if it's a string
        json_path = Path(file_path)

        # Check if the file exists
        if not json_path.exists():
            details = f"Attempted to load Library JSON file. Failed because no file could be found at the specified path: {json_path}"
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Load the JSON
        try:
            with json_path.open("r") as f:
                library_data = json.load(f)
        except json.JSONDecodeError:
            details = f"Attempted to load Library JSON file. Failed because the file at path {json_path} was improperly formatted."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()
        # Extract library information
        try:
            library_name = library_data["name"]
            library_metadata = library_data.get("metadata", {})
            nodes_metadata = library_data.get("nodes", [])
        except KeyError as e:
            details = f"Attempted to load Library JSON file from '{file_path}'. Failed because it was missing required field in library metadata: {e}"
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
            details = f"Attempted to load Library JSON file from '{file_path}'. Failed because a Library '{library_name}' already exists. Error: {err}."
            logger.error(details)
            return RegisterLibraryFromFileResultFailure()

        # Update library metadata
        library._metadata = library_metadata

        # Process each node in the metadata
        for node_meta in nodes_metadata:
            try:
                class_name = node_meta["class_name"]
                node_file_path = node_meta["file_path"]
                node_metadata = node_meta.get("metadata", {})

                # Resolve relative path to absolute path
                node_file_path = Path(node_file_path)
                if not node_file_path.is_absolute():
                    node_file_path = base_dir / node_file_path

                # Dynamically load the module containing the node class
                node_class = self._load_class_from_file(node_file_path, class_name)

                # Register the node type with the library
                library.register_new_node_type(node_class, metadata=node_metadata)

            except (KeyError, ImportError, AttributeError) as e:
                details = f"Attempted to load Library JSON file from '{file_path}'. Failed due to an error loading node '{node_meta.get('class_name', 'unknown')}': {e}"
                logger.error(details)
                return RegisterLibraryFromFileResultFailure()

        # Success!
        details = f"Successfully loaded Library '{library_name}' from JSON file at {file_path}"
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
                GriptapeNodes().handle_request(library_load_request)

    # TODO(griptape): Move to WorkflowManager
    def _register_workflows_from_config(self, config_section: str) -> None:  # noqa: C901, PLR0912, PLR0915 (need lots of branches for error checking)
        config_mgr = GriptapeNodes().ConfigManager()
        workflows_to_register = config_mgr.get_config_value(config_section)
        successful_registrations = []
        failed_registrations = []
        if workflows_to_register is not None:
            for workflow_to_register in workflows_to_register:
                try:
                    workflow_detail = WorkflowSettingsDetail(
                        file_name=workflow_to_register["file_name"],
                        is_griptape_provided=workflow_to_register["is_griptape_provided"],
                    )
                except Exception as err:
                    err_str = f"Error attempting to get info about workflow to register '{workflow_to_register}': {err}. SKIPPING IT."
                    failed_registrations.append(workflow_to_register)
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
                    failed_registrations.append(final_file_path)
                    # SKIP IT
                    continue

                try:
                    successful_metadata_result = cast("LoadWorkflowMetadataResultSuccess", load_metadata_result)
                except Exception as err:
                    err_str = f"Error attempting to get info about workflow to register '{final_file_path}': {err}. SKIPPING IT."
                    failed_registrations.append(final_file_path)
                    logger.error(err_str)
                    continue

                workflow_metadata = successful_metadata_result.metadata

                # Prepend the image paths appropriately.
                if workflow_metadata.image is not None:
                    if workflow_detail.is_griptape_provided:
                        workflow_metadata.image = workflow_metadata.image
                    else:
                        workflow_metadata.image = config_mgr.workspace_path.joinpath(workflow_metadata.image)

                # Register it as a success.
                workflow_register_request = RegisterWorkflowRequest(
                    metadata=workflow_metadata, file_name=str(final_file_path)
                )
                register_result = GriptapeNodes().handle_request(workflow_register_request)

                details = f"'{workflow_metadata.name}' ({final_file_path!s})"

                if register_result.succeeded():
                    # put this in the good pile
                    successful_registrations.append(details)
                else:
                    # not-so-good pile
                    failed_registrations.append(details)

        if len(successful_registrations) == 0 and len(failed_registrations) == 0:
            logger.info("No workflows were registered.")
        if len(successful_registrations) > 0:
            details = "Workflows successfully registered:"
            for successful_registration in successful_registrations:
                details = f"{details}\n\t{successful_registration}"
            logger.info(details)
        if len(failed_registrations) > 0:
            details = "Workflows that FAILED to register:"
            for failed_registration in failed_registrations:
                details = f"{details}\n\t{failed_registration}"
            logger.error(details)


def __getattr__(name) -> logging.Logger:
    """Convenience function so that node authors only need to write 'logger.debug()'."""
    if name == "logger":
        return logger
    msg = f"module '{__name__}' has no attribute '{name}'"
    raise AttributeError(msg)
