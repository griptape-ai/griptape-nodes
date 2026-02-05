"""ParameterFileLocation - parameter type for file paths with save policies."""

from typing import Any

from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.file_location import FileLocation
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.parameter_events import GetConnectionsForParameterResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload


class ParameterFileLocation(Parameter):
    """Parameter type for FileLocation values.

    Accepts FileLocation objects, string paths, or None.
    Provides a .save() method that handles all three cases.
    """

    def __init__(
        self,
        name: str,
        tooltip: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize ParameterFileLocation.

        Args:
            name: Parameter name
            tooltip: Tooltip text for UI
            **kwargs: Additional Parameter arguments (default_value, converters, validators, ui_options, etc.)
        """
        # Extract converters from kwargs if provided
        converters_from_kwargs = kwargs.pop("converters", None)
        file_location_converters = list(converters_from_kwargs) if converters_from_kwargs else []

        def _normalize_file_location(value: Any) -> Any:
            """Normalize value - keep FileLocation objects, convert strings."""
            if value is None:
                return None
            if isinstance(value, str):
                # Keep strings as-is (including empty strings for UI display)
                return value
            if isinstance(value, FileLocation):
                # Keep FileLocation objects as-is - they'll be used in save()
                return value
            if isinstance(value, dict):
                # Handle deserialization from workflow
                return FileLocation.from_dict(value)
            return value

        file_location_converters.insert(0, _normalize_file_location)

        # Extract traits and allowed_modes from kwargs
        traits_from_kwargs = kwargs.pop("traits", None)
        file_location_traits = set(traits_from_kwargs) if traits_from_kwargs else set()

        allowed_modes = kwargs.get("allowed_modes", {ParameterMode.OUTPUT, ParameterMode.INPUT, ParameterMode.PROPERTY})

        # Only add button if parameter accepts input connections
        if ParameterMode.INPUT in allowed_modes:
            file_location_traits.add(
                Button(
                    icon="cog",
                    size="icon",
                    variant="secondary",
                    position="before",
                    tooltip="Create and connect a ResolveFilePath node",
                    on_click=lambda button, button_details: self._create_path_resolver_callback(
                        name, button, button_details
                    ),
                )
            )

        super().__init__(
            name=name,
            type="str",
            input_types=["FileLocation", "str"],
            output_type="str",
            tooltip=tooltip,
            converters=file_location_converters,
            traits=file_location_traits,
            **kwargs,
        )

    def _create_path_resolver_callback(
        self,
        param_name: str,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Create and connect a ResolveFilePath node to this file_path parameter."""
        node_name = self._node_context.name if self._node_context else None
        if not node_name:
            return NodeMessageResult(
                success=False,
                details="Cannot create resolver: parameter has no parent node",
                response=button_details,
                altered_workflow_state=False,
            )

        # Check if parameter already has an incoming connection
        connections_result = RetainedMode.get_connections_for_parameter(parameter_name=param_name, node_name=node_name)

        if (
            isinstance(connections_result, GetConnectionsForParameterResultSuccess)
            and connections_result.has_incoming_connections()
        ):
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: {param_name} parameter already has an incoming connection",
                response=button_details,
                altered_workflow_state=False,
            )

        # Create ResolveFilePath node positioned to the left
        create_result = RetainedMode.create_node_relative_to(
            reference_node_name=node_name,
            new_node_type="ResolveFilePath",
            offset_side="left",
            offset_x=-750,  # Negative offset to position to the left of the reference node
            offset_y=0,
            lock=False,
        )

        if not isinstance(create_result, str):
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to create ResolveFilePath node",
                response=button_details,
                altered_workflow_state=False,
            )

        resolve_node_name = create_result

        # Connect ResolveFilePath.file_location to this parameter
        connection_result = RetainedMode.connect(
            source=f"{resolve_node_name}.file_location", destination=f"{node_name}.{param_name}"
        )

        if not connection_result.succeeded():
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to connect {resolve_node_name}.file_location to {param_name}",
                response=button_details,
                altered_workflow_state=True,  # Node was created
            )

        # Success path
        return NodeMessageResult(
            success=True,
            details=f"{node_name}: Created and connected {resolve_node_name}",
            response=button_details,
            altered_workflow_state=True,
        )

    def save(
        self,
        data: bytes,
        *,
        use_direct_save: bool = True,
        skip_metadata_injection: bool = False,
    ) -> str:
        """Save data using this parameter's current value.

        Handles two cases:
        - str: use string path with default policies
        - FileLocation: delegate to FileLocation.save() with configured policies

        Args:
            data: Binary data to save
            use_direct_save: Whether to save directly without cloud storage
            skip_metadata_injection: Whether to skip metadata injection

        Returns:
            URL of the saved file for UI display

        Raises:
            ValueError: If parameter value is None or empty string
            TypeError: If parameter value is an unexpected type
            FileExistsError: If file exists and policy is FAIL
            RuntimeError: If save operation fails
        """
        if not self._node_context:
            error_msg = f"{self.name}: Parameter has no parent node context"
            raise RuntimeError(error_msg)

        value = self._node_context.get_parameter_value(self.name)

        if value is None or (isinstance(value, str) and not value):
            error_msg = f"{self._node_context.name}: {self.name} parameter value is None or empty string"
            raise ValueError(error_msg)

        if isinstance(value, str):
            file_name = value
        elif isinstance(value, FileLocation):
            # FileLocation has policies configured, use its save method
            return value.save(
                data,
                use_direct_save=use_direct_save,
                skip_metadata_injection=skip_metadata_injection,
            )
        else:
            error_msg = f"{self._node_context.name}: {self.name} has unexpected value type: {type(value)}"
            raise TypeError(error_msg)

        # For string case, use StaticFilesManager with default policies
        return GriptapeNodes.StaticFilesManager().save_static_file(
            data=data,
            file_name=file_name,
            existing_file_policy=ExistingFilePolicy.OVERWRITE,
            use_direct_save=use_direct_save,
            skip_metadata_injection=skip_metadata_injection,
        )
