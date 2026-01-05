from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import semver

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.app_events import (
    EngineHeartbeatRequest,
    EngineHeartbeatResultFailure,
    EngineHeartbeatResultSuccess,
    GetEngineVersionRequest,
    GetEngineVersionResultFailure,
    GetEngineVersionResultSuccess,
)
from griptape_nodes.retained_mode.events.base_events import (
    GriptapeNodeEvent,
    ResultPayloadFailure,
)
from griptape_nodes.retained_mode.events.flow_events import (
    DeleteFlowRequest,
)
from griptape_nodes.utils.metaclasses import SingletonMeta
from griptape_nodes.utils.version_utils import engine_version

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import (
        AppPayload,
        RequestPayload,
        ResultPayload,
    )
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
    from griptape_nodes.retained_mode.managers.mcp_manager import MCPManager
    from griptape_nodes.retained_mode.managers.model_manager import ModelManager
    from griptape_nodes.retained_mode.managers.node_manager import NodeManager
    from griptape_nodes.retained_mode.managers.object_manager import ObjectManager
    from griptape_nodes.retained_mode.managers.operation_manager import (
        OperationDepthManager,
    )
    from griptape_nodes.retained_mode.managers.os_manager import OSManager
    from griptape_nodes.retained_mode.managers.project_manager import ProjectManager
    from griptape_nodes.retained_mode.managers.resource_manager import ResourceManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
    from griptape_nodes.retained_mode.managers.session_manager import SessionManager
    from griptape_nodes.retained_mode.managers.static_files_manager import (
        StaticFilesManager,
    )
    from griptape_nodes.retained_mode.managers.sync_manager import SyncManager
    from griptape_nodes.retained_mode.managers.user_manager import UserManager
    from griptape_nodes.retained_mode.managers.variable_manager import (
        VariablesManager,
    )
    from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
        VersionCompatibilityManager,
    )
    from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager


logger = logging.getLogger("griptape_nodes")


class GriptapeNodes(metaclass=SingletonMeta):
    # CRITICAL managers - initialized eagerly for workflow execution
    _event_manager: EventManager
    _config_manager: ConfigManager
    _secrets_manager: SecretsManager
    _resource_manager: ResourceManager
    _library_manager: LibraryManager
    _node_manager: NodeManager
    _flow_manager: FlowManager
    _context_manager: ContextManager
    _workflow_manager: WorkflowManager
    _workflow_variables_manager: VariablesManager
    _os_manager: OSManager
    _model_manager: ModelManager

    # OPTIONAL managers - initialized lazily when accessed
    _engine_identity_manager: EngineIdentityManager | None = None
    _session_manager: SessionManager | None = None
    _static_files_manager: StaticFilesManager | None = None
    _agent_manager: AgentManager | None = None
    _mcp_manager: MCPManager | None = None
    _sync_manager: SyncManager | None = None
    _user_manager: UserManager | None = None
    _project_manager: ProjectManager | None = None
    _arbitrary_code_exec_manager: ArbitraryCodeExecManager | None = None
    _object_manager: ObjectManager | None = None
    _version_compatibility_manager: VersionCompatibilityManager | None = None
    _operation_depth_manager: OperationDepthManager | None = None

    def __init__(self) -> None:
        from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
        from griptape_nodes.retained_mode.managers.context_manager import ContextManager
        from griptape_nodes.retained_mode.managers.event_manager import EventManager
        from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
        from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
        from griptape_nodes.retained_mode.managers.model_manager import ModelManager
        from griptape_nodes.retained_mode.managers.node_manager import NodeManager
        from griptape_nodes.retained_mode.managers.os_manager import OSManager
        from griptape_nodes.retained_mode.managers.resource_manager import ResourceManager
        from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
        from griptape_nodes.retained_mode.managers.variable_manager import (
            VariablesManager,
        )
        from griptape_nodes.retained_mode.managers.workflow_manager import (
            WorkflowManager,
        )

        # Initialize only CRITICAL managers for workflow execution
        if not hasattr(self, "_event_manager"):
            # Core event system
            self._event_manager = EventManager()

            # Configuration and resources
            self._resource_manager = ResourceManager(self._event_manager)
            self._config_manager = ConfigManager(self._event_manager)
            self._secrets_manager = SecretsManager(self._config_manager, self._event_manager)

            # File system and models
            self._os_manager = OSManager(self._event_manager)
            self._model_manager = ModelManager(self._event_manager)

            # Core workflow execution managers
            self._library_manager = LibraryManager(self._event_manager)
            self._node_manager = NodeManager(self._event_manager)
            self._flow_manager = FlowManager(self._event_manager)
            self._context_manager = ContextManager(self._event_manager)
            self._workflow_manager = WorkflowManager(self._event_manager)
            self._workflow_variables_manager = VariablesManager(self._event_manager)

            # Assign handlers for core requests
            self._event_manager.assign_manager_to_request_type(
                GetEngineVersionRequest, self.handle_engine_version_request
            )
            self._event_manager.assign_manager_to_request_type(
                EngineHeartbeatRequest, self.handle_engine_heartbeat_request
            )

    @classmethod
    def get_instance(cls) -> GriptapeNodes:
        """Helper method to get the singleton instance."""
        return cls()

    @classmethod
    def handle_request(
        cls,
        request: RequestPayload,
    ) -> ResultPayload:
        """Synchronous request handler."""
        event_mgr = GriptapeNodes.EventManager()

        try:
            result_event = event_mgr.handle_request(request=request)
            # Only queue result event if not suppressed
            if not event_mgr.should_suppress_event(result_event):
                event_mgr.put_event(GriptapeNodeEvent(wrapped_event=result_event))
        except Exception as e:
            logger.exception(
                "Unhandled exception while processing request of type %s. "
                "Consider saving your work and restarting the engine if issues persist."
                "Request: %s",
                type(request).__name__,
                request,
            )
            return ResultPayloadFailure(
                exception=e, result_details=f"Unhandled exception while processing {type(request).__name__}: {e}"
            )
        else:
            return result_event.result

    @classmethod
    async def ahandle_request(cls, request: RequestPayload) -> ResultPayload:
        """Asynchronous request handler.

        Args:
            request: The request payload to handle.
        """
        event_mgr = GriptapeNodes.EventManager()

        try:
            result_event = await event_mgr.ahandle_request(request=request)
            # Only queue result event if not suppressed
            if not event_mgr.should_suppress_event(result_event):
                await event_mgr.aput_event(GriptapeNodeEvent(wrapped_event=result_event))
        except Exception as e:
            logger.exception(
                "Unhandled exception while processing async request of type %s. "
                "Consider saving your work and restarting the engine if issues persist."
                "Request: %s",
                type(request).__name__,
                request,
            )
            return ResultPayloadFailure(
                exception=e, result_details=f"Unhandled exception while processing async {type(request).__name__}: {e}"
            )
        else:
            return result_event.result

    @classmethod
    async def broadcast_app_event(cls, app_event: AppPayload) -> None:
        event_mgr = GriptapeNodes.get_instance()._event_manager
        await event_mgr.broadcast_app_event(app_event)

    @classmethod
    def get_session_id(cls) -> str | None:
        return GriptapeNodes.SessionManager().active_session_id

    @classmethod
    def get_engine_id(cls) -> str | None:
        return GriptapeNodes.EngineIdentityManager().active_engine_id

    # CRITICAL manager accessors - always available
    @classmethod
    def EventManager(cls) -> EventManager:
        return GriptapeNodes.get_instance()._event_manager

    @classmethod
    def ConfigManager(cls) -> ConfigManager:
        return GriptapeNodes.get_instance()._config_manager

    @classmethod
    def SecretsManager(cls) -> SecretsManager:
        return GriptapeNodes.get_instance()._secrets_manager

    @classmethod
    def ResourceManager(cls) -> ResourceManager:
        return GriptapeNodes.get_instance()._resource_manager

    @classmethod
    def LibraryManager(cls) -> LibraryManager:
        return GriptapeNodes.get_instance()._library_manager

    @classmethod
    def NodeManager(cls) -> NodeManager:
        return GriptapeNodes.get_instance()._node_manager

    @classmethod
    def FlowManager(cls) -> FlowManager:
        return GriptapeNodes.get_instance()._flow_manager

    @classmethod
    def ContextManager(cls) -> ContextManager:
        return GriptapeNodes.get_instance()._context_manager

    @classmethod
    def WorkflowManager(cls) -> WorkflowManager:
        return GriptapeNodes.get_instance()._workflow_manager

    @classmethod
    def VariablesManager(cls) -> VariablesManager:
        return GriptapeNodes.get_instance()._workflow_variables_manager

    @classmethod
    def OSManager(cls) -> OSManager:
        return GriptapeNodes.get_instance()._os_manager

    @classmethod
    def ModelManager(cls) -> ModelManager:
        return GriptapeNodes.get_instance()._model_manager

    # OPTIONAL manager accessors - lazy initialized
    @classmethod
    def ObjectManager(cls) -> ObjectManager:
        instance = GriptapeNodes.get_instance()
        if instance._object_manager is None:
            from griptape_nodes.retained_mode.managers.object_manager import ObjectManager

            instance._object_manager = ObjectManager(instance._event_manager)
        return instance._object_manager

    @classmethod
    def ArbitraryCodeExecManager(cls) -> ArbitraryCodeExecManager:
        instance = GriptapeNodes.get_instance()
        if instance._arbitrary_code_exec_manager is None:
            from griptape_nodes.retained_mode.managers.arbitrary_code_exec_manager import (
                ArbitraryCodeExecManager,
            )

            instance._arbitrary_code_exec_manager = ArbitraryCodeExecManager(instance._event_manager)
        return instance._arbitrary_code_exec_manager

    @classmethod
    def OperationDepthManager(cls) -> OperationDepthManager:
        instance = GriptapeNodes.get_instance()
        if instance._operation_depth_manager is None:
            from griptape_nodes.retained_mode.managers.operation_manager import (
                OperationDepthManager,
            )

            instance._operation_depth_manager = OperationDepthManager(instance._config_manager)
        return instance._operation_depth_manager

    @classmethod
    def StaticFilesManager(cls) -> StaticFilesManager:
        instance = GriptapeNodes.get_instance()
        if instance._static_files_manager is None:
            from griptape_nodes.retained_mode.managers.static_files_manager import (
                StaticFilesManager,
            )

            instance._static_files_manager = StaticFilesManager(
                instance._config_manager, instance._secrets_manager, instance._event_manager
            )
        return instance._static_files_manager

    @classmethod
    def AgentManager(cls) -> AgentManager:
        instance = GriptapeNodes.get_instance()
        if instance._agent_manager is None:
            from griptape_nodes.retained_mode.managers.agent_manager import AgentManager

            instance._agent_manager = AgentManager(cls.StaticFilesManager(), instance._event_manager)
        return instance._agent_manager

    @classmethod
    def VersionCompatibilityManager(cls) -> VersionCompatibilityManager:
        instance = GriptapeNodes.get_instance()
        if instance._version_compatibility_manager is None:
            from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
                VersionCompatibilityManager,
            )

            instance._version_compatibility_manager = VersionCompatibilityManager(instance._event_manager)
        return instance._version_compatibility_manager

    @classmethod
    def SessionManager(cls) -> SessionManager:
        instance = GriptapeNodes.get_instance()
        if instance._session_manager is None:
            from griptape_nodes.retained_mode.managers.session_manager import SessionManager

            instance._session_manager = SessionManager(cls.EngineIdentityManager(), instance._event_manager)
        return instance._session_manager

    @classmethod
    def MCPManager(cls) -> MCPManager:
        instance = GriptapeNodes.get_instance()
        if instance._mcp_manager is None:
            from griptape_nodes.retained_mode.managers.mcp_manager import MCPManager

            instance._mcp_manager = MCPManager(instance._event_manager, instance._config_manager)
        return instance._mcp_manager

    @classmethod
    def EngineIdentityManager(cls) -> EngineIdentityManager:
        instance = GriptapeNodes.get_instance()
        if instance._engine_identity_manager is None:
            from griptape_nodes.retained_mode.managers.engine_identity_manager import EngineIdentityManager

            instance._engine_identity_manager = EngineIdentityManager(instance._event_manager)
        return instance._engine_identity_manager

    @classmethod
    def SyncManager(cls) -> SyncManager:
        instance = GriptapeNodes.get_instance()
        if instance._sync_manager is None:
            from griptape_nodes.retained_mode.managers.sync_manager import SyncManager

            instance._sync_manager = SyncManager(instance._event_manager, instance._config_manager)
        return instance._sync_manager

    @classmethod
    def UserManager(cls) -> UserManager:
        instance = GriptapeNodes.get_instance()
        if instance._user_manager is None:
            from griptape_nodes.retained_mode.managers.user_manager import UserManager

            instance._user_manager = UserManager(instance._secrets_manager)
        return instance._user_manager

    @classmethod
    def ProjectManager(cls) -> ProjectManager:
        instance = GriptapeNodes.get_instance()
        if instance._project_manager is None:
            from griptape_nodes.retained_mode.managers.project_manager import ProjectManager

            instance._project_manager = ProjectManager(
                instance._event_manager, instance._config_manager, instance._secrets_manager
            )
        return instance._project_manager

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
            engine_ver = semver.VersionInfo.parse(engine_version)
            return GetEngineVersionResultSuccess(
                major=engine_ver.major,
                minor=engine_ver.minor,
                patch=engine_ver.patch,
                result_details="Engine version retrieved successfully.",
            )
        except Exception as err:
            details = f"Attempted to get engine version. Failed due to '{err}'."
            logger.error(details)
            return GetEngineVersionResultFailure(result_details=details)

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
            engine_name = GriptapeNodes.EngineIdentityManager().engine_name

            # Get user and organization
            user = GriptapeNodes.UserManager().user
            user_organization = GriptapeNodes.UserManager().user_organization

            return EngineHeartbeatResultSuccess(
                heartbeat_id=request.heartbeat_id,
                engine_version=engine_version,
                engine_name=engine_name,
                engine_id=GriptapeNodes.EngineIdentityManager().active_engine_id,
                session_id=GriptapeNodes.SessionManager().active_session_id,
                timestamp=datetime.now(tz=UTC).isoformat(),
                user=user,
                user_organization=user_organization,
                result_details="Engine heartbeat successful",
                **instance_info,
                **workflow_info,
            )
        except Exception as err:
            details = f"Failed to handle engine heartbeat: {err}"
            logger.error(details)
            return EngineHeartbeatResultFailure(heartbeat_id=request.heartbeat_id, result_details=details)

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
