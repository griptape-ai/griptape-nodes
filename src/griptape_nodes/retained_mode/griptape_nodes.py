from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.app_events import (
    AppConnectionEstablished,
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
    RequestPayload,
    ResultPayload,
    ResultPayloadFailure,
)
from griptape_nodes.retained_mode.events.flow_events import (
    DeleteFlowRequest,
)
from griptape_nodes.utils.metaclasses import SingletonMeta
from griptape_nodes.utils.version_utils import engine_version

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.agent_manager import AgentManager
    from griptape_nodes.retained_mode.managers.arbitrary_code_exec_manager import (
        ArbitraryCodeExecManager,
    )
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.context_manager import ContextManager
    from griptape_nodes.retained_mode.managers.engine_identity_manager import EngineIdentityManager
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
    from griptape_nodes.retained_mode.managers.session_manager import SessionManager
    from griptape_nodes.retained_mode.managers.static_files_manager import (
        StaticFilesManager,
    )
    from griptape_nodes.retained_mode.managers.sync_manager import SyncManager
    from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
        VersionCompatibilityManager,
    )
    from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager


logger = logging.getLogger("griptape_nodes")


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

    def __hash__(self) -> int:
        """Hash function for Version."""
        return hash((self.major, self.minor, self.patch))


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
    _session_manager: SessionManager
    _engine_identity_manager: EngineIdentityManager
    _sync_manager: SyncManager

    def __init__(self) -> None:
        from griptape_nodes.retained_mode.managers.agent_manager import AgentManager
        from griptape_nodes.retained_mode.managers.arbitrary_code_exec_manager import (
            ArbitraryCodeExecManager,
        )
        from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
        from griptape_nodes.retained_mode.managers.context_manager import ContextManager
        from griptape_nodes.retained_mode.managers.engine_identity_manager import EngineIdentityManager
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
        from griptape_nodes.retained_mode.managers.session_manager import SessionManager
        from griptape_nodes.retained_mode.managers.static_files_manager import (
            StaticFilesManager,
        )
        from griptape_nodes.retained_mode.managers.sync_manager import SyncManager
        from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
            VersionCompatibilityManager,
        )
        from griptape_nodes.retained_mode.managers.workflow_manager import (
            WorkflowManager,
        )

        # Initialize only if our managers haven't been created yet
        if not hasattr(self, "_event_manager"):
            self._event_manager = EventManager()
            self._config_manager = ConfigManager(self._event_manager)
            self._os_manager = OSManager(self._event_manager)
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
            self._session_manager = SessionManager(self._event_manager)
            self._engine_identity_manager = EngineIdentityManager(self._event_manager)
            self._sync_manager = SyncManager(self._event_manager, self._config_manager)

            # Assign handlers now that these are created.
            self._event_manager.assign_manager_to_request_type(
                GetEngineVersionRequest, self.handle_engine_version_request
            )
            self._event_manager.assign_manager_to_request_type(
                AppStartSessionRequest, self.handle_session_start_request
            )
            self._event_manager.assign_manager_to_request_type(AppEndSessionRequest, self.handle_session_end_request)
            self._event_manager.add_listener_to_app_event(AppConnectionEstablished, self.on_app_connection_established)
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
    def handle_request(
        cls,
        request: RequestPayload,
        *,
        response_topic: str | None = None,
        request_id: str | None = None,
    ) -> ResultPayload:
        event_mgr = GriptapeNodes.EventManager()
        obj_depth_mgr = GriptapeNodes.OperationDepthManager()
        workflow_mgr = GriptapeNodes.WorkflowManager()
        try:
            return event_mgr.handle_request(
                request=request,
                operation_depth_mgr=obj_depth_mgr,
                workflow_mgr=workflow_mgr,
                response_topic=response_topic,
                request_id=request_id,
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
        return GriptapeNodes.SessionManager().get_active_session_id()

    @classmethod
    def get_engine_id(cls) -> str | None:
        return GriptapeNodes.EngineIdentityManager().get_active_engine_id()

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
    def OSManager(cls) -> OSManager:
        return GriptapeNodes.get_instance()._os_manager

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
    def SessionManager(cls) -> SessionManager:
        return GriptapeNodes.get_instance()._session_manager

    @classmethod
    def EngineIdentityManager(cls) -> EngineIdentityManager:
        return GriptapeNodes.get_instance()._engine_identity_manager

    @classmethod
    def SyncManager(cls) -> SyncManager:
        return GriptapeNodes.get_instance()._sync_manager

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

    def on_app_connection_established(self, _payload: AppConnectionEstablished) -> None:
        from griptape_nodes.app.app import subscribe_to_topic

        # Subscribe to request topic (engine discovery)
        subscribe_to_topic("request")

        # Get engine ID and subscribe to engine_id/request
        engine_id = GriptapeNodes.get_engine_id()
        if engine_id:
            subscribe_to_topic(f"engines/{engine_id}/request")
        else:
            logger.warning("Engine ID not available for subscription")

        # Get session ID and subscribe to session_id/request if available
        session_id = GriptapeNodes.get_session_id()
        if session_id:
            topic = f"sessions/{session_id}/request"
            subscribe_to_topic(topic)
        else:
            logger.info("No session ID available for subscription")

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
            return GetEngineVersionResultFailure(result_details=details)
        except Exception as err:
            details = f"Attempted to get engine version. Failed due to '{err}'."
            logger.error(details)
            return GetEngineVersionResultFailure(result_details=details)

    def handle_session_start_request(self, request: AppStartSessionRequest) -> ResultPayload:  # noqa: ARG002
        from griptape_nodes.app.app import subscribe_to_topic

        current_session_id = GriptapeNodes.SessionManager().get_active_session_id()
        if current_session_id is None:
            # Client wants a new session
            current_session_id = uuid.uuid4().hex
            GriptapeNodes.SessionManager().save_session(current_session_id)
            details = f"New session '{current_session_id}' started at {datetime.now(tz=UTC)}."
            logger.info(details)
        else:
            details = f"Session '{current_session_id}' already active. Joining..."

        topic = f"sessions/{current_session_id}/request"
        subscribe_to_topic(topic)
        logger.info("Subscribed to new session topic: %s", topic)

        return AppStartSessionResultSuccess(current_session_id)

    def handle_session_end_request(self, _: AppEndSessionRequest) -> ResultPayload:
        from griptape_nodes.app.app import unsubscribe_from_topic

        try:
            previous_session_id = GriptapeNodes.SessionManager().get_active_session_id()
            if previous_session_id is None:
                details = "No active session to end."
                logger.info(details)
            else:
                details = f"Session '{previous_session_id}' ended at {datetime.now(tz=UTC)}."
                logger.info(details)
                GriptapeNodes.SessionManager().clear_saved_session()

            unsubscribe_topic = f"sessions/{previous_session_id}/request"
            unsubscribe_from_topic(unsubscribe_topic)

            return AppEndSessionResultSuccess(session_id=previous_session_id)
        except Exception as err:
            details = f"Failed to end session due to '{err}'."
            logger.error(details)
            return AppEndSessionResultFailure(result_details=details)

    def handle_get_session_request(self, _: AppGetSessionRequest) -> ResultPayload:
        return AppGetSessionResultSuccess(session_id=GriptapeNodes.SessionManager().get_active_session_id())

    def handle_session_heartbeat_request(self, request: SessionHeartbeatRequest) -> ResultPayload:  # noqa: ARG002
        """Handle session heartbeat requests.

        Simply verifies that the session is active and responds with success.
        """
        try:
            active_session_id = GriptapeNodes.SessionManager().get_active_session_id()
            if active_session_id is None:
                details = "Session heartbeat received but no active session found"
                logger.warning(details)
                return SessionHeartbeatResultFailure(result_details=details)

            details = f"Session heartbeat successful for session: {active_session_id}"
            logger.debug(details)
            return SessionHeartbeatResultSuccess()
        except Exception as err:
            details = f"Failed to handle session heartbeat: {err}"
            logger.error(details)
            return SessionHeartbeatResultFailure(result_details=details)

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
            engine_name = GriptapeNodes.EngineIdentityManager().get_engine_name()

            logger.debug("Engine heartbeat successful")
            return EngineHeartbeatResultSuccess(
                heartbeat_id=request.heartbeat_id,
                engine_version=engine_version,
                engine_name=engine_name,
                engine_id=GriptapeNodes.EngineIdentityManager().get_active_engine_id(),
                session_id=GriptapeNodes.SessionManager().get_active_session_id(),
                timestamp=datetime.now(tz=UTC).isoformat(),
                **instance_info,
                **workflow_info,
            )
        except Exception as err:
            details = f"Failed to handle engine heartbeat: {err}"
            logger.error(details)
            return EngineHeartbeatResultFailure(heartbeat_id=request.heartbeat_id, result_details=details)

    def handle_get_engine_name_request(self, request: GetEngineNameRequest) -> ResultPayload:  # noqa: ARG002
        """Handle requests to get the current engine name."""
        try:
            engine_name = GriptapeNodes.EngineIdentityManager().get_engine_name()
            logger.debug("Retrieved engine name: %s", engine_name)
            return GetEngineNameResultSuccess(engine_name=engine_name)
        except Exception as err:
            error_message = f"Failed to get engine name: {err}"
            logger.error(error_message)
            return GetEngineNameResultFailure(error_message=error_message, result_details=error_message)

    def handle_set_engine_name_request(self, request: SetEngineNameRequest) -> ResultPayload:
        """Handle requests to set a new engine name."""
        try:
            # Validate engine name (basic validation)
            if not request.engine_name or not request.engine_name.strip():
                error_message = "Engine name cannot be empty"
                logger.warning(error_message)
                return SetEngineNameResultFailure(error_message=error_message, result_details=error_message)

            # Set the new engine name
            GriptapeNodes.EngineIdentityManager().set_engine_name(request.engine_name.strip())
            logger.info("Engine name set to: %s", request.engine_name.strip())
            return SetEngineNameResultSuccess(engine_name=request.engine_name.strip())

        except Exception as err:
            error_message = f"Failed to set engine name: {err}"
            logger.error(error_message)
            return SetEngineNameResultFailure(error_message=error_message, result_details=error_message)

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

        return instance_info

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
