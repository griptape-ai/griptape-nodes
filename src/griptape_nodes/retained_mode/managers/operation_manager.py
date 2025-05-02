from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from types import TracebackType

    from griptape_nodes.retained_mode.events.arbitrary_python_events import RunArbitraryPythonStringRequest
    from griptape_nodes.retained_mode.events.base_events import RequestPayload
    from griptape_nodes.retained_mode.events.config_events import (
        GetConfigCategoryRequest,
        GetConfigValueRequest,
        SetConfigCategoryRequest,
        SetConfigValueRequest,
    )
    from griptape_nodes.retained_mode.events.connection_events import (
        CreateConnectionRequest,
        DeleteConnectionRequest,
        ListConnectionsForNodeRequest,
    )
    from griptape_nodes.retained_mode.events.execution_events import (
        CancelFlowRequest,
        ContinueExecutionStepRequest,
        GetFlowStateRequest,
        ResolveNodeRequest,
        SingleExecutionStepRequest,
        SingleNodeStepRequest,
        StartFlowRequest,
        UnresolveFlowRequest,
    )
    from griptape_nodes.retained_mode.events.flow_events import (
        CreateFlowRequest,
        DeleteFlowRequest,
        ListFlowsInFlowRequest,
        ListNodesInFlowRequest,
    )
    from griptape_nodes.retained_mode.events.library_events import (
        GetNodeMetadataFromLibraryRequest,
        ListNodeTypesInLibraryRequest,
        ListRegisteredLibrariesRequest,
    )
    from griptape_nodes.retained_mode.events.node_events import (
        CreateNodeRequest,
        DeleteNodeRequest,
        GetNodeMetadataRequest,
        GetNodeResolutionStateRequest,
        ListParametersOnNodeRequest,
        SetNodeMetadataRequest,
    )
    from griptape_nodes.retained_mode.events.parameter_events import (
        AddParameterToNodeRequest,
        AlterParameterDetailsRequest,
        GetParameterDetailsRequest,
        GetParameterValueRequest,
        RemoveParameterFromNodeRequest,
        SetParameterValueRequest,
    )
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager


def handle_parameter_tooltips(payload: Any, params: Any) -> list:
    """Handle converting tooltips to the correct format for RetainedMode."""
    tooltip = getattr(payload, "tooltip", "")
    if tooltip is not None:
        params.append(f'tooltip="{tooltip}"')

    if getattr(payload, "tooltip_as_input", None) is not None:
        params.append(f'tooltip_as_input="{payload.tooltip_as_input}"')

    if getattr(payload, "tooltip_as_property", None) is not None:
        params.append(f'tooltip_as_property="{payload.tooltip_as_property}"')

    if getattr(payload, "tooltip_as_output", None) is not None:
        params.append(f'tooltip_as_output="{payload.tooltip_as_output}"')

    if getattr(payload, "ui_options", None) is not None:
        payload_ui = payload.ui_options
        if payload_ui:
            params.append(f"ui_options={payload_ui}")  # No quotes for object
    return params


class PayloadConverter:
    """Converter class that takes Payload objects and executes the appropriate RetainedMode methods.

    This acts as an adapter layer between Payload-based API calls and RetainedMode.
    """

    @staticmethod
    def execute(payload: RequestPayload) -> str:
        """Main entry point for executing payloads.

        Takes a payload object and routes it to the appropriate handler method based on its type.

        Args:
            payload: A RequestPayload object containing the operation details

        Returns:
            ResultPayload: The result of the operation
        """
        # Get the type of the payload to determine which handler to use
        payload_type = type(payload).__name__

        # Get the handler method for this payload type
        handler_method = getattr(PayloadConverter, f"_handle_{payload_type}", None)

        if handler_method is None:
            command_string = f"api.handle_request({payload})"
        else:
            command_string = handler_method(payload)

        return command_string

    @staticmethod
    def _handle_DeleteFlowRequest(payload: DeleteFlowRequest) -> str:
        """Handle DeleteFlowRequest payloads."""
        return f"""cmd.delete_flow(flow_name="{payload.flow_name}")"""

    @staticmethod
    def _handle_ListFlowsInFlowRequest(payload: ListFlowsInFlowRequest) -> str:
        """Handle ListFlowsInFlowRequest payloads."""
        return f"""cmd.get_flows(parent_flow_name="{getattr(payload, "parent_flow_name", None)}")"""

    @staticmethod
    def _handle_ListNodesInFlowRequest(payload: ListNodesInFlowRequest) -> str:
        """Handle ListNodesInFlowRequest payloads."""
        return f"""cmd.get_nodes_in_flow(flow_name="{payload.flow_name}")"""

    # NODE OPERATION HANDLERS

    @staticmethod
    def _handle_CreateNodeRequest(payload: CreateNodeRequest) -> str:
        """Handle CreateNodeRequest payloads."""
        # Start with the required parameter
        params = [f'node_type="{payload.node_type}"']

        # Add optional parameters only if they are not None
        if getattr(payload, "specific_library_name", None) is not None:
            params.append(f'specific_library_name="{payload.specific_library_name}"')

        if getattr(payload, "node_name", None) is not None:
            params.append(f'node_name="{payload.node_name}"')

        if getattr(payload, "override_parent_flow_name", None) is not None:
            params.append(f'parent_flow_name="{payload.override_parent_flow_name}"')

        if getattr(payload, "metadata", None) is not None:
            params.append(f"metadata={payload.metadata}")  # Note: no quotes for metadata as it's an object

        # Join all parameters with commas
        command_params = ",".join(params)

        return f"""cmd.create_node({command_params})"""

    @staticmethod
    def _handle_DeleteNodeRequest(payload: DeleteNodeRequest) -> str:
        """Handle DeleteNodeRequest payloads."""
        return f"""cmd.delete_node(node_name="{payload.node_name}")"""

    @staticmethod
    def _handle_GetNodeResolutionStateRequest(payload: GetNodeResolutionStateRequest) -> str:
        """Handle GetNodeResolutionStateRequest payloads."""
        return f"""cmd.get_resolution_state_for_node(node_name="{payload.node_name}")"""

    @staticmethod
    def _handle_GetNodeMetadataRequest(payload: GetNodeMetadataRequest) -> str:
        """Handle GetNodeMetadataRequest payloads."""
        return f"""cmd.get_metadata_for_node(node_name="{payload.node_name}")"""

    @staticmethod
    def _handle_SetNodeMetadataRequest(payload: SetNodeMetadataRequest) -> str:
        """Handle SetNodeMetadataRequest payloads."""
        return f"""cmd.set_metadata_for_node(node_name="{payload.node_name}",metadata="{payload.metadata}")"""

    @staticmethod
    def _handle_ListConnectionsForNodeRequest(payload: ListConnectionsForNodeRequest) -> str:
        """Handle ListConnectionsForNodeRequest payloads."""
        return f"""cmd.get_connections_for_node(node_name="{payload.node_name}")"""

    @staticmethod
    def _handle_ListParametersOnNodeRequest(payload: ListParametersOnNodeRequest) -> str:
        """Handle ListParametersOnNodeRequest payloads."""
        return f"""cmd.list_params(node="{payload.node_name}")"""

    # PARAMETER OPERATION HANDLERS

    @staticmethod
    def _handle_AddParameterToNodeRequest(payload: AddParameterToNodeRequest) -> str:
        """Handle AddParameterToNodeRequest payloads."""
        # Start with required parameters
        params = [
            f'node_name="{payload.node_name}"',
            f'parameter_name="{payload.parameter_name}"',
            f"input_types={payload.input_types}",  # No quotes as it's likely a list/object
            "edit=False",
        ]

        # Add optional parameters only if they are not None
        default_value = payload.default_value
        if isinstance(default_value, str):
            default_value = rf"'{default_value}'"
        params.append(f"default_value={payload.default_value}")  # No quotes for potential non-string values

        # Empty string is a valid value for tooltip, so only exclude if None
        params = handle_parameter_tooltips(payload, params)

        # For boolean values, include them only if they differ from defaults
        if getattr(payload, "mode_allowed_input", True) is not True:
            params.append(f"mode_allowed_input={payload.mode_allowed_input}")

        if getattr(payload, "mode_allowed_property", True) is not True:
            params.append(f"mode_allowed_property={payload.mode_allowed_property}")

        if getattr(payload, "mode_allowed_output", True) is not True:
            params.append(f"mode_allowed_output={payload.mode_allowed_output}")

        # Join all parameters with commas
        command_params = ",".join(params)

        return f"""cmd.add_param({command_params})"""

    @staticmethod
    def _handle_AlterParameterDetailsRequest(payload: AlterParameterDetailsRequest) -> str:
        """Handle AlterParameterDetailsRequest payloads."""
        # Start with required parameters
        params = [
            f'node_name="{payload.node_name}"',
            f'parameter_name="{payload.parameter_name}"',
            f"input_types={payload.input_types}",  # No quotes as it's likely a list/object
            "edit=True",
        ]

        # Add optional parameters only if they are not None
        default_value = payload.default_value
        if isinstance(default_value, str):
            default_value = rf"'{default_value}'"
        params.append(f"default_value={payload.default_value}")  # No quotes for potential non-string values

        # Empty string is a valid value for tooltip, so only exclude if None
        params = handle_parameter_tooltips(payload, params)

        # For boolean values, include them only if they differ from defaults
        if getattr(payload, "mode_allowed_input", True) is not True:
            params.append(f"mode_allowed_input={payload.mode_allowed_input}")

        if getattr(payload, "mode_allowed_property", True) is not True:
            params.append(f"mode_allowed_property={payload.mode_allowed_property}")

        if getattr(payload, "mode_allowed_output", True) is not True:
            params.append(f"mode_allowed_output={payload.mode_allowed_output}")

        # Join all parameters with commas
        command_params = ",".join(params)

        return f"""cmd.add_param({command_params})"""

    @staticmethod
    def _handle_RemoveParameterFromNodeRequest(payload: RemoveParameterFromNodeRequest) -> str:
        """Handle RemoveParameterFromNodeRequest payloads."""
        return f"""cmd.del_param(node_name="{payload.node_name}",parameter_name="{payload.parameter_name}")"""

    @staticmethod
    def _handle_GetParameterDetailsRequest(payload: GetParameterDetailsRequest) -> str:
        """Handle GetParameterDetailsRequest payloads."""
        return f"""cmd.param_info("{payload.node_name}.{payload.parameter_name}")"""

    @staticmethod
    def _handle_GetParameterValueRequest(payload: GetParameterValueRequest) -> str:
        """Handle GetParameterValueRequest payloads."""
        return f"""cmd.get_value("{payload.node_name}.{payload.parameter_name}")"""

    @staticmethod
    def _handle_SetParameterValueRequest(payload: SetParameterValueRequest) -> str:
        """Handle SetParameterValueRequest payloads."""
        max_length = 100  # Adjust this as needed

        # Safely convert payload.value to string
        try:
            value_str = str(payload.value)
        except Exception:
            value_str = "<unconvertible value>"

        # Handle multiline strings
        value_str = value_str.replace("\n", "\\n").replace("\r", "\\r")

        # Escape quotes to prevent breaking the command string
        value_str = value_str.replace('"', '\\"')

        # Truncate if necessary
        if len(value_str) > max_length:
            # Be careful with Unicode when truncating
            truncated_value = value_str[:max_length] + "..."
        else:
            truncated_value = value_str

        return f"""cmd.set_value("{payload.node_name}.{payload.parameter_name}",value="{truncated_value}")"""

    # CONNECTION OPERATION HANDLERS

    @staticmethod
    def _handle_CreateConnectionRequest(payload: CreateConnectionRequest) -> str:
        """Handle CreateConnectionRequest payloads."""
        source = f"{payload.source_node_name}.{payload.source_parameter_name}"
        destination = f"{payload.target_node_name}.{payload.target_parameter_name}"
        return f"""cmd.connect(source="{source}",destination="{destination}")"""

    @staticmethod
    def _handle_DeleteConnectionRequest(payload: DeleteConnectionRequest) -> str:
        """Handle DeleteConnectionRequest payloads."""
        return f"""cmd.delete_connection(source_node_name="{payload.source_node_name}",source_param_name="{payload.source_parameter_name}",target_node_name="{payload.target_node_name}",target_param_name="{payload.target_parameter_name}")"""

    # LIBRARY OPERATION HANDLERS

    @staticmethod
    def _handle_ListRegisteredLibrariesRequest(payload: ListRegisteredLibrariesRequest) -> str:  # noqa: ARG004
        """Handle ListRegisteredLibrariesRequest payloads."""
        return """cmd.get_available_libraries()"""

    @staticmethod
    def _handle_ListNodeTypesInLibraryRequest(payload: ListNodeTypesInLibraryRequest) -> str:
        """Handle ListNodeTypesInLibraryRequest payloads."""
        return f"""cmd.get_node_types_in_library(library_name="{payload.library}")"""

    @staticmethod
    def _handle_GetNodeMetadataFromLibraryRequest(payload: GetNodeMetadataFromLibraryRequest) -> str:
        """Handle GetNodeMetadataFromLibraryRequest payloads."""
        return f"""cmd.get_node_metadata_from_library(library_name="{payload.library}",node_type_name="{payload.node_type}")"""

    # FLOW EXECUTION HANDLERS

    @staticmethod
    def _handle_StartFlowRequest(payload: StartFlowRequest) -> str:
        """Handle StartFlowRequest payloads."""
        return f"""cmd.run_flow(flow_name="{payload.flow_name}")"""

    @staticmethod
    def _handle_ResolveNodeRequest(payload: ResolveNodeRequest) -> str:
        """Handle ResolveNodeRequest payloads."""
        return f"""cmd.run_node(node_name="{payload.node_name}")"""

    @staticmethod
    def _handle_SingleNodeStepRequest(payload: SingleNodeStepRequest) -> str:
        """Handle SingleNodeStepRequest payloads."""
        return f"""cmd.single_step(flow_name="{payload.flow_name}")"""

    @staticmethod
    def _handle_SingleExecutionStepRequest(payload: SingleExecutionStepRequest) -> str:
        """Handle SingleExecutionStepRequest payloads."""
        return f"""cmd.single_execution_step(flow_name="{payload.flow_name}")"""

    @staticmethod
    def _handle_ContinueExecutionStepRequest(payload: ContinueExecutionStepRequest) -> str:
        """Handle ContinueExecutionStepRequest payloads."""
        return f"""cmd.continue_flow(flow_name="{payload.flow_name}")"""

    @staticmethod
    def _handle_UnresolveFlowRequest(payload: UnresolveFlowRequest) -> str:
        """Handle UnresolveFlowRequest payloads."""
        return f"""cmd.reset_flow(flow_name="{payload.flow_name}")"""

    @staticmethod
    def _handle_CancelFlowRequest(payload: CancelFlowRequest) -> str:
        """Handle CancelFlowRequest payloads."""
        return f"""cmd.cancel_flow(flow_name="{payload.flow_name}")"""

    @staticmethod
    def _handle_GetFlowStateRequest(payload: GetFlowStateRequest) -> str:
        """Handle GetFlowStateRequest payloads."""
        return f"""cmd.get_flow_state(flow_name="{payload.flow_name}")"""

    # ARBITRARY PYTHON EXECUTION HANDLER

    @staticmethod
    def _handle_RunArbitraryPythonStringRequest(payload: RunArbitraryPythonStringRequest) -> str:
        """Handle RunArbitraryPythonStringRequest payloads."""
        return f"""cmd.run_arbitrary_python(python_str="{payload.python_string}")"""

    # CONFIG MANAGER HANDLERS

    @staticmethod
    def _handle_GetConfigValueRequest(payload: GetConfigValueRequest) -> str:
        """Handle GetConfigValueRequest payloads."""
        return f"""cmd.get_config_value(category_and_key="{payload.category_and_key}")"""

    @staticmethod
    def _handle_SetConfigValueRequest(payload: SetConfigValueRequest) -> str:
        """Handle SetConfigValueRequest payloads."""
        return f"""cmd.set_config_value(category_and_key="{payload.category_and_key}",value="{payload.value}")"""

    @staticmethod
    def _handle_GetConfigCategoryRequest(payload: GetConfigCategoryRequest) -> str:
        """Handle GetConfigCategoryRequest payloads."""
        return f"""cmd.get_config_category(category="{getattr(payload, "category", None)}")"""

    @staticmethod
    def _handle_SetConfigCategoryRequest(payload: SetConfigCategoryRequest) -> str:
        """Handle SetConfigCategoryRequest payloads."""
        return f"""cmd.set_config_category(category="{getattr(payload, "category", None)}",contents="{payload.contents}")"""

    # FLOW OPERATIONS
    @staticmethod
    def _handle_CreateFlowRequest(payload: CreateFlowRequest) -> str:
        """Handle CreateFlowRequest payloads."""
        params = []
        if getattr(payload, "flow_name", None) is not None:
            params.append(f'flow_name="{payload.flow_name}"')
        if getattr(payload, "parent_flow_name", None) is not None:
            params.append(f'flow_name="{payload.flow_name}"')

        command_params = ",".join(params)

        return f"""cmd.create_flow({command_params})"""

    # GENERIC HANDLERS FOR PAYLOADS WITHOUT SPECIFIC HANDLERS


class OperationDepthManager:
    # Class variable to track current depth across all instances
    _depth = 0
    payload_converter: PayloadConverter
    should_echo_events: bool = True
    events_to_echo: set[str]

    def __init__(self, config_mgr: ConfigManager) -> None:
        self.payload_converter = PayloadConverter()

        # Ask the config manager for the list of events we want echoed.
        config_events = config_mgr.get_config_value("app_events.events_to_echo_as_retained_mode")
        self.events_to_echo = set(config_events)

    def __enter__(self) -> Self:
        # Increment depth when entering context
        self._depth += 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        # Decrement depth when exiting context
        self._depth -= 1

    def get_depth(self) -> int:
        return self._depth

    def is_top_level(self) -> bool:
        return self._depth == 1

    def request_retained_mode_translation(self, request: RequestPayload) -> str | None:
        if self.should_echo_events:
            request_type = type(request)
            if (request_type.__name__ in self.events_to_echo) or "*" in self.events_to_echo:
                retained_mode_str = self.retained_mode_code(request)
                return retained_mode_str
        return None

    def retained_mode_code(self, request: RequestPayload) -> str:
        retained_mode_value = self.payload_converter.execute(request)
        # save to a workflow.py.
        # is there an effective way to do this without duplicating commands?
        return retained_mode_value
