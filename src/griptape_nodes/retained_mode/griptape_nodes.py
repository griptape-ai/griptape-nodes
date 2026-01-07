from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import semver

from griptape_nodes.exe_types.flow import ControlFlow
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
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
    from griptape_nodes.retained_mode.managers.mcp_manager import MCPManager
    from griptape_nodes.retained_mode.managers.model_manager import ModelManager
    from griptape_nodes.retained_mode.managers.node_manager import NodeManager
    from griptape_nodes.retained_mode.managers.object_manager import ObjectManager
    from griptape_nodes.retained_mode.managers.os_manager import OSManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
    from griptape_nodes.retained_mode.managers.static_files_manager import (
        StaticFilesManager,
    )
    from griptape_nodes.retained_mode.managers.variable_manager import (
        VariablesManager,
    )


logger = logging.getLogger("griptape_nodes")


class GriptapeNodes(metaclass=SingletonMeta):
    _event_manager: EventManager
    _os_manager: OSManager
    _config_manager: ConfigManager
    _secrets_manager: SecretsManager
    _object_manager: ObjectManager
    _node_manager: NodeManager
    _flow_manager: FlowManager
    _library_manager: LibraryManager
    _model_manager: ModelManager
    _workflow_variables_manager: VariablesManager
    _static_files_manager: StaticFilesManager
    _mcp_manager: MCPManager

    def __init__(self) -> None:
        from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
        from griptape_nodes.retained_mode.managers.event_manager import EventManager
        from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
        from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
        from griptape_nodes.retained_mode.managers.mcp_manager import MCPManager
        from griptape_nodes.retained_mode.managers.model_manager import ModelManager
        from griptape_nodes.retained_mode.managers.node_manager import NodeManager
        from griptape_nodes.retained_mode.managers.object_manager import ObjectManager
        from griptape_nodes.retained_mode.managers.os_manager import OSManager
        from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
        from griptape_nodes.retained_mode.managers.static_files_manager import (
            StaticFilesManager,
        )
        from griptape_nodes.retained_mode.managers.variable_manager import (
            VariablesManager,
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
            self._library_manager = LibraryManager(self._event_manager)
            self._model_manager = ModelManager(self._event_manager)
            self._workflow_variables_manager = VariablesManager(self._event_manager)
            self._static_files_manager = StaticFilesManager(
                self._config_manager, self._secrets_manager, self._event_manager
            )
            self._mcp_manager = MCPManager(self._event_manager, self._config_manager)

            # Assign handlers now that these are created.
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
        return None

    @classmethod
    def get_engine_id(cls) -> str | None:
        return None

    @classmethod
    def EventManager(cls) -> EventManager:
        return GriptapeNodes.get_instance()._event_manager

    @classmethod
    def LibraryManager(cls) -> LibraryManager:
        return GriptapeNodes.get_instance()._library_manager

    @classmethod
    def ModelManager(cls) -> ModelManager:
        return GriptapeNodes.get_instance()._model_manager

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
    def ConfigManager(cls) -> ConfigManager:
        return GriptapeNodes.get_instance()._config_manager

    @classmethod
    def OSManager(cls) -> OSManager:
        return GriptapeNodes.get_instance()._os_manager

    @classmethod
    def SecretsManager(cls) -> SecretsManager:
        return GriptapeNodes.get_instance()._secrets_manager

    @classmethod
    def StaticFilesManager(cls) -> StaticFilesManager:
        return GriptapeNodes.get_instance()._static_files_manager

    @classmethod
    def MCPManager(cls) -> MCPManager:
        return GriptapeNodes.get_instance()._mcp_manager

    @classmethod
    def VariablesManager(cls) -> VariablesManager:
        return GriptapeNodes.get_instance()._workflow_variables_manager

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

            return EngineHeartbeatResultSuccess(
                heartbeat_id=request.heartbeat_id,
                engine_version=engine_version,
                engine_name=None,
                engine_id=None,
                session_id=None,
                timestamp=datetime.now(tz=UTC).isoformat(),
                user=None,
                user_organization=None,
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

        return workflow_info
