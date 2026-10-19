from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.engine import EngineScoped
from griptape_nodes.retained_mode.events.workflow_events import (
    GetVariableSubstitutionEnabledRequest,
    GetVariableSubstitutionEnabledResultFailure,
    GetVariableSubstitutionEnabledResultSuccess,
    SetVariableSubstitutionEnabledRequest,
    SetVariableSubstitutionEnabledResultFailure,
    SetVariableSubstitutionEnabledResultNotAlteredSuccess,
    SetVariableSubstitutionEnabledResultSuccess,
)
from griptape_nodes.retained_mode.request_handlers import handles

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime


logger = logging.getLogger("griptape_nodes")


class VariableSubstitution(EngineScoped):
    def __init__(self, event_manager: EventManager, *, engine: Engine | None = None) -> None:
        super().__init__(engine)
        event_manager.register_request_handlers(self)

    def is_enabled(self) -> bool:
        """Whether variable substitution is on for the current workflow. On when no workflow is open.

        Node code reads it through `VariableResolver`, which has no runtime to hand.
        """
        workflow = self.engine.current_workflow_or_none()
        if workflow is None:
            return True
        return workflow.variables.substitution_enabled

    @handles(GetVariableSubstitutionEnabledRequest)
    def on_get_variable_substitution_enabled_request(
        self,
        request: GetVariableSubstitutionEnabledRequest,  # noqa: ARG002
        workflow: WorkflowRuntime,
    ) -> ResultPayload:
        """Return whether variable substitution is enabled for the workflow."""
        if not workflow.context.has_current_workflow():
            return GetVariableSubstitutionEnabledResultFailure(
                result_details="Attempted to get variable substitution enabled. Failed because no workflow is active."
            )
        enabled = workflow.variables.substitution_enabled
        return GetVariableSubstitutionEnabledResultSuccess(
            result_details=f"Variable substitution is {'enabled' if enabled else 'disabled'} for the current workflow.",
            enabled=enabled,
        )

    @handles(SetVariableSubstitutionEnabledRequest)
    def on_set_variable_substitution_enabled_request(
        self, request: SetVariableSubstitutionEnabledRequest, workflow: WorkflowRuntime
    ) -> ResultPayload:
        """Enable or disable variable substitution for the workflow.

        Held by the open workflow. When the workflow is saved, the code generator bakes a
        SetVariableSubstitutionEnabledRequest call into build_workflow() so the flag is restored on
        every subsequent load, including direct script execution.
        """
        if not workflow.context.has_current_workflow():
            return SetVariableSubstitutionEnabledResultFailure(
                result_details="Attempted to set variable substitution enabled. Failed because no workflow is active."
            )
        workflow_name = workflow.context.get_current_workflow_name()
        workflow.variables.substitution_enabled = request.enabled
        details = (
            f"Variable substitution {'enabled' if request.enabled else 'disabled'} for workflow '{workflow_name}'."
        )
        if request.initial_setup:
            return SetVariableSubstitutionEnabledResultNotAlteredSuccess(result_details=details)
        return SetVariableSubstitutionEnabledResultSuccess(result_details=details)
