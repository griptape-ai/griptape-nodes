from __future__ import annotations

import importlib.metadata
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import IO, TYPE_CHECKING, Any, TextIO

import httpx

from griptape_nodes.exe_types.core_types import BaseNodeElement, Parameter, ParameterContainer, ParameterGroup
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.app_events import (
    AppEndSessionRequest,
    AppEndSessionResultFailure,
    AppEndSessionResultSuccess,
    AppGetSessionRequest,
    AppGetSessionResultSuccess,
    AppStartSessionRequest,
    AppStartSessionResultSuccess,
    EngineHeartbeatRequest,
    EngineHeartbeatResultFailure,
    EngineHeartbeatResultSuccess,
    GetEngineNameRequest,
    GetEngineNameResultFailure,
    GetEngineNameResultSuccess,
    GetEngineVersionRequest,
    GetEngineVersionResultFailure,
    GetEngineVersionResultSuccess,
    SessionHeartbeatRequest,
    SessionHeartbeatResultFailure,
    SessionHeartbeatResultSuccess,
    SetEngineNameRequest,
    SetEngineNameResultFailure,
    SetEngineNameResultSuccess,
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
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    DeleteFlowRequest,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AlterParameterDetailsRequest,
)
from griptape_nodes.retained_mode.utils.engine_identity import EngineIdentity
from griptape_nodes.retained_mode.utils.session_persistence import SessionPersistence
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.retained_mode.managers.agent_manager import AgentManager
    from griptape_nodes.retained_mode.managers.arbitrary_code_exec_manager import (
        ArbitraryCodeExecManager,
    )
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.context_manager import ContextManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
    from griptape_nodes.retained_mode.managers.node_manager import NodeManager
    from griptape_nodes.retained_mode.managers.object_manager import ObjectManager
    from griptape_nodes.retained_mode.managers.operation_manager import (
        OperationDepthManager,
    )
    from griptape_nodes.retained_mode.managers.os_manager import OSManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
    from griptape_nodes.retained_mode.managers.static_files_manager import (
        StaticFilesManager,
    )
    from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
        VersionCompatibilityManager,
    )
    from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager


logger = logging.getLogger("griptape_nodes")


engine_version = importlib.metadata.version("griptape_nodes")


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

    def __lt__(self, other: Version) -> bool:
        """Less than comparison."""
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: Version) -> bool:
        """Less than or equal comparison."""
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)

    def __gt__(self, other: Version) -> bool:
        """Greater than comparison."""
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __ge__(self, other: Version) -> bool:
        """Greater than or equal comparison."""
        return (self.major, self.minor, self.patch) >= (other.major, other.minor, other.patch)

    def __eq__(self, other: Version) -> bool:  # type: ignore[override]
        """Equality comparison."""
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)


class GriptapeNodes(metaclass=SingletonMeta):
    _event_manager: EventManager
    _os_manager: OSManager
    _config_manager: ConfigManager
    _secrets_manager: SecretsManager
    _object_manager: ObjectManager
    _node_manager: NodeManager
    _flow_manager: FlowManager
    _context_manager: ContextManager
    _library_manager: LibraryManager
    _workflow_manager: WorkflowManager
    _arbitrary_code_exec_manager: ArbitraryCodeExecManager
    _operation_depth_manager: OperationDepthManager
    _static_files_manager: StaticFilesManager
    _agent_manager: AgentManager
    _version_compatibility_manager: VersionCompatibilityManager

    def __init__(self) -> None:
        from griptape_nodes.retained_mode.managers.agent_manager import AgentManager
        from griptape_nodes.retained_mode.managers.arbitrary_code_exec_manager import (
            ArbitraryCodeExecManager,
        )
        from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
        from griptape_nodes.retained_mode.managers.context_manager import ContextManager
        from griptape_nodes.retained_mode.managers.event_manager import EventManager
        from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
        from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
        from griptape_nodes.retained_mode.managers.node_manager import NodeManager
        from griptape_nodes.retained_mode.managers.object_manager import ObjectManager
        from griptape_nodes.retained_mode.managers.operation_manager import (
            OperationDepthManager,
        )
        from griptape_nodes.retained_mode.managers.os_manager import OSManager
        from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
        from griptape_nodes.retained_mode.managers.static_files_manager import (
            StaticFilesManager,
        )
        from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
            VersionCompatibilityManager,
        )
        from griptape_nodes.retained_mode.managers.workflow_manager import (
            WorkflowManager,
        )

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
            self._static_files_manager = StaticFilesManager(
                self._config_manager, self._secrets_manager, self._event_manager
            )
            self._agent_manager = AgentManager(self._static_files_manager, self._event_manager)
            self._version_compatibility_manager = VersionCompatibilityManager(self._event_manager)

            # Assign handlers now that these are created.
            self._event_manager.assign_manager_to_request_type(
                GetEngineVersionRequest, self.handle_engine_version_request
            )
            self._event_manager.assign_manager_to_request_type(
                AppStartSessionRequest, self.handle_session_start_request
            )
            self._event_manager.assign_manager_to_request_type(AppEndSessionRequest, self.handle_session_end_request)
            self._event_manager.assign_manager_to_request_type(AppGetSessionRequest, self.handle_get_session_request)
            self._event_manager.assign_manager_to_request_type(
                SessionHeartbeatRequest, self.handle_session_heartbeat_request
            )
            self._event_manager.assign_manager_to_request_type(
                EngineHeartbeatRequest, self.handle_engine_heartbeat_request
            )
            self._event_manager.assign_manager_to_request_type(
                GetEngineNameRequest, self.handle_get_engine_name_request
            )
            self._event_manager.assign_manager_to_request_type(
                SetEngineNameRequest, self.handle_set_engine_name_request
            )

    @classmethod
    def get_instance(cls) -> GriptapeNodes:
        """Helper method to get the singleton instance."""
        return cls()

    @classmethod
    def handle_request(cls, request: RequestPayload) -> ResultPayload:
        event_mgr = GriptapeNodes.EventManager()
        obj_depth_mgr = GriptapeNodes.OperationDepthManager()
        workflow_mgr = GriptapeNodes.WorkflowManager()

        try:
            return event_mgr.handle_request(
                request=request,
                operation_depth_mgr=obj_depth_mgr,
                workflow_mgr=workflow_mgr,
            )
        except Exception as e:
            logger.exception(
                "Unhandled exception while processing request of type %s. "
                "Consider saving your work and restarting the engine if issues persist.",
                type(request).__name__,
            )
            return ResultPayloadFailure(exception=e)

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
    def StaticFilesManager(cls) -> StaticFilesManager:
        return GriptapeNodes.get_instance()._static_files_manager

    @classmethod
    def AgentManager(cls) -> AgentManager:
        return GriptapeNodes.get_instance()._agent_manager

    @classmethod
    def VersionCompatibilityManager(cls) -> VersionCompatibilityManager:
        return GriptapeNodes.get_instance()._version_compatibility_manager

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
                    raise RuntimeError(e) from e
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
        try:
            engine_ver = Version.from_string(engine_version)
            if engine_ver:
                return GetEngineVersionResultSuccess(
                    major=engine_ver.major,
                    minor=engine_ver.minor,
                    patch=engine_ver.patch,
                )
            details = f"Attempted to get engine version. Failed because version string '{engine_ver}' wasn't in expected major.minor.patch format."
            logger.error(details)
            return GetEngineVersionResultFailure()
        except Exception as err:
            details = f"Attempted to get engine version. Failed due to '{err}'."
            logger.error(details)
            return GetEngineVersionResultFailure()

    def handle_session_start_request(self, request: AppStartSessionRequest) -> ResultPayload:  # noqa: ARG002
        current_session_id = BaseEvent._session_id
        if current_session_id is None:
            # Client wants a new session
            current_session_id = uuid.uuid4().hex
            BaseEvent._session_id = current_session_id
            # Persist the session ID to XDG state directory
            SessionPersistence.persist_session(current_session_id)
            details = f"New session '{current_session_id}' started at {datetime.now(tz=UTC)}."
            logger.info(details)
        else:
            details = f"Session '{current_session_id}' already active. Joining..."

        return AppStartSessionResultSuccess(current_session_id)

    def handle_session_end_request(self, _: AppEndSessionRequest) -> ResultPayload:
        try:
            previous_session_id = BaseEvent._session_id
            if BaseEvent._session_id is None:
                details = "No active session to end."
                logger.info(details)
            else:
                details = f"Session '{BaseEvent._session_id}' ended at {datetime.now(tz=UTC)}."
                logger.info(details)
                BaseEvent._session_id = None
                # Clear the persisted session ID from XDG state directory
                SessionPersistence.clear_persisted_session()

            return AppEndSessionResultSuccess(session_id=previous_session_id)
        except Exception as err:
            details = f"Failed to end session due to '{err}'."
            logger.error(details)
            return AppEndSessionResultFailure()

    def handle_get_session_request(self, _: AppGetSessionRequest) -> ResultPayload:
        return AppGetSessionResultSuccess(session_id=BaseEvent._session_id)

    def handle_session_heartbeat_request(self, request: SessionHeartbeatRequest) -> ResultPayload:  # noqa: ARG002
        """Handle session heartbeat requests.

        Simply verifies that the session is active and responds with success.
        """
        try:
            if BaseEvent._session_id is None:
                logger.warning("Session heartbeat received but no active session found")
                return SessionHeartbeatResultFailure()

            logger.debug("Session heartbeat successful for session: %s", BaseEvent._session_id)
            return SessionHeartbeatResultSuccess()
        except Exception as err:
            logger.error("Failed to handle session heartbeat: %s", err)
            return SessionHeartbeatResultFailure()

    def handle_engine_heartbeat_request(self, request: EngineHeartbeatRequest) -> ResultPayload:
        """Handle engine heartbeat requests.

        Returns engine status information including version, session state, and system metrics.
        """
        try:
            # Get instance information based on environment variables
            instance_info = self._get_instance_info()

            # Get current workflow information
            workflow_info = self._get_current_workflow_info()

            # Get engine name
            engine_name = EngineIdentity.get_engine_name()

            logger.debug("Engine heartbeat successful")
            return EngineHeartbeatResultSuccess(
                heartbeat_id=request.heartbeat_id,
                engine_version=engine_version,
                engine_name=engine_name,
                engine_id=BaseEvent._engine_id,
                session_id=BaseEvent._session_id,
                timestamp=datetime.now(tz=UTC).isoformat(),
                **instance_info,
                **workflow_info,
            )
        except Exception as err:
            logger.error("Failed to handle engine heartbeat: %s", err)
            return EngineHeartbeatResultFailure(heartbeat_id=request.heartbeat_id)

    def handle_get_engine_name_request(self, request: GetEngineNameRequest) -> ResultPayload:  # noqa: ARG002
        """Handle requests to get the current engine name."""
        try:
            engine_name = EngineIdentity.get_engine_name()
            logger.debug("Retrieved engine name: %s", engine_name)
            return GetEngineNameResultSuccess(engine_name=engine_name)
        except Exception as err:
            error_message = f"Failed to get engine name: {err}"
            logger.error(error_message)
            return GetEngineNameResultFailure(error_message=error_message)

    def handle_set_engine_name_request(self, request: SetEngineNameRequest) -> ResultPayload:
        """Handle requests to set a new engine name."""
        try:
            # Validate engine name (basic validation)
            if not request.engine_name or not request.engine_name.strip():
                error_message = "Engine name cannot be empty"
                logger.warning(error_message)
                return SetEngineNameResultFailure(error_message=error_message)

            # Set the new engine name
            EngineIdentity.set_engine_name(request.engine_name.strip())
            logger.info("Engine name set to: %s", request.engine_name.strip())
            return SetEngineNameResultSuccess(engine_name=request.engine_name.strip())

        except Exception as err:
            error_message = f"Failed to set engine name: {err}"
            logger.error(error_message)
            return SetEngineNameResultFailure(error_message=error_message)

    def _get_instance_info(self) -> dict[str, str | None]:
        """Get instance information from environment variables.

        Returns instance type, region, provider, and public IP information if available.
        """
        instance_info: dict[str, str | None] = {
            "instance_type": os.getenv("GTN_INSTANCE_TYPE"),
            "instance_region": os.getenv("GTN_INSTANCE_REGION"),
            "instance_provider": os.getenv("GTN_INSTANCE_PROVIDER"),
        }

        # Determine deployment type based on presence of instance environment variables
        instance_info["deployment_type"] = "griptape_hosted" if any(instance_info.values()) else "local"

        # Get public IP address
        public_ip = self._get_public_ip()
        if public_ip:
            instance_info["public_ip"] = public_ip

        return instance_info

    def _get_public_ip(self) -> str | None:
        """Get the public IP address of this device.

        Returns the public IP address if available, None otherwise.
        """
        try:
            # Try multiple services in case one is down
            services = [
                "https://api.ipify.org",
                "https://ipinfo.io/ip",
                "https://icanhazip.com",
            ]

            for service in services:
                try:
                    with httpx.Client(timeout=5.0) as client:
                        response = client.get(service)
                        response.raise_for_status()
                        public_ip = response.text.strip()
                        if public_ip:
                            logger.debug("Retrieved public IP from %s: %s", service, public_ip)
                            return public_ip
                except Exception as err:
                    logger.debug("Failed to get public IP from %s: %s", service, err)
                    continue
            logger.warning("Unable to retrieve public IP from any service")
        except Exception as err:
            logger.warning("Failed to get public IP: %s", err)
            return None
        else:
            return None

    def _get_current_workflow_info(self) -> dict[str, Any]:
        """Get information about the currently loaded workflow.

        Returns workflow name, file path, and status information if available.
        """
        workflow_info = {
            "current_workflow": None,
            "workflow_file_path": None,
            "has_active_flow": False,
        }

        try:
            context_manager = self._context_manager

            # Check if there's an active workflow
            if context_manager.has_current_workflow():
                workflow_name = context_manager.get_current_workflow_name()
                workflow_info["current_workflow"] = workflow_name
                workflow_info["has_active_flow"] = context_manager.has_current_flow()

                # Get workflow file path from registry
                if WorkflowRegistry.has_workflow_with_name(workflow_name):
                    workflow = WorkflowRegistry.get_workflow_by_name(workflow_name)
                    absolute_path = WorkflowRegistry.get_complete_file_path(workflow.file_path)
                    workflow_info["workflow_file_path"] = absolute_path

        except Exception as err:
            logger.warning("Failed to get current workflow info: %s", err)

        return workflow_info


def create_flows_in_order(flow_name: str, flow_manager: FlowManager, created_flows: list, file: IO) -> list | None:
    """Creates flows in the correct order based on their dependencies."""
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
    """Handles the creation and saving of flows."""
    flow_manager = GriptapeNodes.FlowManager()
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
    """Handles the creation and saving of parameters for a node."""
    parameter_details = ""
    saved_properly = True
    # Get all parameters, even ones that aren't direct children.
    for parameter in node.root_ui_element.find_elements_by_type(BaseNodeElement):
        if isinstance(parameter, (Parameter, ParameterGroup, ParameterContainer)):
            param_dict = parameter.to_dict()
            # Create the parameter, or alter it on the existing node
            if isinstance(parameter, Parameter) and parameter.user_defined:
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
            if not isinstance(parameter, ParameterGroup) and (
                parameter.name in node.parameter_values or parameter.name in node.parameter_output_values
            ):
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


def manage_alter_details(parameter: Parameter | ParameterGroup, base_node_obj: BaseNode) -> dict:
    """Alters the details of a parameter based on the base node object."""
    if isinstance(parameter, Parameter):
        base_param = base_node_obj.get_parameter_by_name(parameter.name)
        if base_param is not None:
            diff = base_param.equals(parameter)
        else:
            return vars(parameter)
    else:
        base_param_group = base_node_obj.get_group_by_name_or_element_id(parameter.name)
        if base_param_group is not None:
            diff = base_param_group.equals(parameter)
        else:
            return vars(parameter)
    return diff


def __getattr__(name: str) -> logging.Logger:
    """Convenience function so that node authors only need to write 'logger.debug()'."""
    if name == "logger":
        return logger
    msg = f"module '{__name__}' has no attribute '{name}'"
    raise AttributeError(msg)
