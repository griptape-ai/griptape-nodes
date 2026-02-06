"""ParameterFileLocation - parameter type for file paths with save policies."""

from typing import Any

from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.file_location import FileLocation
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.parameter_events import GetConnectionsForParameterResultSuccess
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

        # Set initial helper text if we have a default value
        # Note: _node_context will be set later when parameter is attached to node
        # So we'll also update helper text in after_value_set()
        self._initial_helper_text_set = False

    def _set_initial_helper_text(self) -> None:
        """Set initial helper text once node context is available."""
        if self._initial_helper_text_set or not self._node_context:
            return

        self._initial_helper_text_set = True
        preview = self.get_resolved_path_preview(index=0)
        if preview:
            self.update_ui_options_key("helper_text", preview)

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
        index: int = 0,
        *,
        use_direct_save: bool = True,
        skip_metadata_injection: bool = False,
    ) -> str:
        """Save data using this parameter's current value.

        Handles two cases:
        - str: treat as macro template, resolve with ProjectManager, use with default policies
        - FileLocation: delegate to FileLocation.save() with configured policies and index

        Args:
            data: Binary data to save
            index: Index for multi-image generation (0 for single image)
            use_direct_save: Whether to save directly without cloud storage
            skip_metadata_injection: Whether to skip metadata injection

        Returns:
            URL of the saved file for UI display

        Raises:
            ValueError: If parameter value is None or empty string
            TypeError: If parameter value is an unexpected type
            FileExistsError: If file exists and policy is FAIL
            RuntimeError: If save operation fails or macro resolution fails
        """
        if not self._node_context:
            error_msg = f"{self.name}: Parameter has no parent node context"
            raise RuntimeError(error_msg)

        value = self._node_context.get_parameter_value(self.name)

        if value is None or (isinstance(value, str) and not value):
            error_msg = f"{self._node_context.name}: {self.name} parameter value is None or empty string"
            raise ValueError(error_msg)

        if isinstance(value, str):
            # Create FileLocation with the string as macro template and default policies
            # Only provide node_name as a variable - don't extract file_name_base/file_extension
            # from the template itself (those are only meaningful in ResolveFilePath with separate filename input)
            variables: dict[str, str | int] = {
                "node_name": self._node_context.name,
            }

            value = FileLocation(
                macro_template=value,
                base_variables=variables,
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
                create_parent_dirs=True,
            )

        if isinstance(value, FileLocation):
            # FileLocation has policies configured, use its save method with index
            return value.save(
                data,
                index=index,
                use_direct_save=use_direct_save,
                skip_metadata_injection=skip_metadata_injection,
            )

        error_msg = f"{self._node_context.name}: {self.name} has unexpected value type: {type(value)}"
        raise TypeError(error_msg)

    def get_resolved_path_preview(self, index: int = 0) -> str | None:
        """Compute what the resolved path would be without saving (dry run).

        Args:
            index: Index for multi-image generation preview (default 0)

        Returns:
            Resolved absolute path string, or None if resolution fails
        """
        if not self._node_context:
            return None

        value = self._node_context.get_parameter_value(self.name)

        if value is None or (isinstance(value, str) and not value):
            return None

        if isinstance(value, str):
            # Create variables dict for macro resolution
            variables: dict[str, str | int] = {
                "node_name": self._node_context.name,
            }
            if index > 0:
                variables["index"] = index

            # Resolve macro template
            from griptape_nodes.common.macro_parser import ParsedMacro
            from griptape_nodes.retained_mode.events.project_events import (
                GetPathForMacroRequest,
                GetPathForMacroResultSuccess,
            )
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            parsed_macro = ParsedMacro(value)
            resolve_request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables=variables)
            result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(resolve_request)

            if isinstance(result, GetPathForMacroResultSuccess):
                return str(result.absolute_path)
            return None

        if isinstance(value, FileLocation):
            # Use FileLocation's __str__() which resolves the path
            return str(value)

        return None

    def after_value_set(self, new_value: Any) -> None:  # noqa: ARG002
        """Update helper text when parameter value changes.

        Args:
            new_value: The new value that was just set
        """
        if not self._node_context:
            return

        # Set initial helper text if not already set
        self._set_initial_helper_text()

        # Compute preview
        preview = self.get_resolved_path_preview(index=0)

        # Update helper text in ui_options
        if preview:
            self.update_ui_options_key("helper_text", preview)
        else:
            # Clear helper text if resolution fails
            ui_options = self.ui_options.copy()
            ui_options.pop("helper_text", None)
            self.ui_options = ui_options
