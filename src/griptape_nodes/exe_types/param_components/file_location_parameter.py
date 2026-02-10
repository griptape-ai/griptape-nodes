"""FileLocationParameter - parameter component for file location UI integration."""

from typing import Any

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.file_location import FileLocation
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.parameter_events import GetConnectionsForParameterResultSuccess
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker


class FileLocationParameter:
    """Parameter component for FileLocation UI integration and file operations.

    This component provides:
    - Parameter creation with proper traits (FileSystemPicker, Button)
    - UI helper text updates showing resolved path preview
    - Button to create/connect ResolveFilePath nodes
    - Instance methods for saving/loading from the parameter

    For working with arbitrary values (not from parameters), use FileLocation directly:
        >>> file_location = FileLocation.from_any(value, base_variables={"node_name": self.name})
        >>> data = await file_location.aload()

    Example:
        >>> # In node __init__:
        >>> self._file_path_param = FileLocationParameter(
        ...     node=self,
        ...     name="file_path",
        ...     default_value="{staticfiles}/output.png",
        ... )
        >>> self._file_path_param.add_parameter()
        >>>
        >>> # In node process() - use instance methods:
        >>> static_url = self._file_path_param.save(data)
        >>> # Or with extra variables:
        >>> static_url = self._file_path_param.save(data, index=i)
    """

    def __init__(
        self,
        node: BaseNode,
        name: str,
        *,
        default_value: Any = None,
        allowed_modes: set[ParameterMode] | None = None,
        tooltip: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize FileLocationParameter component.

        Args:
            node: Parent node instance
            name: Parameter name
            default_value: Default parameter value
            allowed_modes: Set of allowed parameter modes (default: INPUT, PROPERTY)
            tooltip: Tooltip text for UI
            **kwargs: Additional parameter options (input_types, output_type, ui_options)
        """
        self._node = node
        self._name = name
        self._default_value = default_value
        self._allowed_modes = allowed_modes or {ParameterMode.INPUT, ParameterMode.PROPERTY}
        self._tooltip = tooltip
        self._input_types = kwargs.get("input_types") or ["FileLocation", "str"]
        self._output_type = kwargs.get("output_type") or "str"
        self._ui_options = kwargs.get("ui_options") or {}
        self._parameter: Parameter | None = None
        self._initial_helper_text_set = False

    def add_parameter(self) -> None:
        """Create and add the parameter to the node with configured traits and converters."""

        def _normalize_file_location(value: Any) -> Any:
            """Normalize value - keep FileLocation objects, convert strings."""
            if value is None:
                return None
            if isinstance(value, str):
                return value
            if isinstance(value, FileLocation):
                return value
            if isinstance(value, dict):
                return FileLocation.from_dict(value)
            return value

        converters = [_normalize_file_location]
        traits: set = set()

        # Add FileSystemPicker trait for file selection
        traits.add(
            FileSystemPicker(
                allow_files=True,
                allow_directories=False,
                multiple=False,
                allow_create=True,
            )
        )

        # Only add button if parameter accepts input connections
        if ParameterMode.INPUT in self._allowed_modes:
            traits.add(
                Button(
                    icon="cog",
                    size="icon",
                    variant="secondary",
                    position="before",
                    tooltip="Create and connect a ResolveFilePath node",
                    on_click=lambda button, button_details: self._create_path_resolver_callback(button, button_details),
                )
            )

        # Create the parameter
        self._parameter = Parameter(
            name=self._name,
            type=self._output_type,
            input_types=self._input_types,
            output_type=self._output_type,
            tooltip=self._tooltip,
            default_value=self._default_value,
            allowed_modes=self._allowed_modes,
            converters=converters,
            traits=traits,
            ui_options=self._ui_options,
        )

        self._node.add_parameter(self._parameter)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:  # noqa: ARG002
        """Update helper text when parameter value changes.

        Args:
            parameter: The parameter that was updated
            value: The new value that was set
        """
        if parameter.name != self._name:
            return

        if not self._parameter:
            return

        # Set initial helper text if not already set
        if not self._initial_helper_text_set:
            self._initial_helper_text_set = True
            preview = self.get_resolved_path_preview()
            if preview:
                self._parameter.update_ui_options_key("helper_text", preview)
            return

        # Compute and update preview
        preview = self.get_resolved_path_preview()
        if preview:
            self._parameter.update_ui_options_key("helper_text", preview)
        else:
            ui_options = self._parameter.ui_options.copy()
            ui_options.pop("helper_text", None)
            self._parameter.ui_options = ui_options

    def _create_path_resolver_callback(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Create and connect a ResolveFilePath node to this file_path parameter."""
        node_name = self._node.name
        if not node_name:
            return NodeMessageResult(
                success=False,
                details="Cannot create resolver: node has no name",
                response=button_details,
                altered_workflow_state=False,
            )

        # Check if parameter already has an incoming connection
        connections_result = RetainedMode.get_connections_for_parameter(parameter_name=self._name, node_name=node_name)

        if (
            isinstance(connections_result, GetConnectionsForParameterResultSuccess)
            and connections_result.has_incoming_connections()
        ):
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: {self._name} parameter already has an incoming connection",
                response=button_details,
                altered_workflow_state=False,
            )

        # Create ResolveFilePath node positioned to the left
        create_result = RetainedMode.create_node_relative_to(
            reference_node_name=node_name,
            new_node_type="ResolveFilePath",
            offset_side="left",
            offset_x=-750,
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
            source=f"{resolve_node_name}.file_location", destination=f"{node_name}.{self._name}"
        )

        if not connection_result.succeeded():
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to connect {resolve_node_name}.file_location to {self._name}",
                response=button_details,
                altered_workflow_state=True,
            )

        return NodeMessageResult(
            success=True,
            details=f"{node_name}: Created and connected {resolve_node_name}",
            response=button_details,
            altered_workflow_state=True,
        )

    def get_resolved_path_preview(self) -> str | None:
        """Compute what the resolved path would be without saving (dry run).

        Returns:
            Resolved absolute path string, or None if resolution fails
        """
        value = self._node.get_parameter_value(self._name)

        if value is None or (isinstance(value, str) and not value):
            return None

        if isinstance(value, str):
            variables: dict[str, str | int] = {
                "node_name": self._node.name,
            }

            parsed_macro = ParsedMacro(value)
            resolve_request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables=variables)
            result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(resolve_request)

            if isinstance(result, GetPathForMacroResultSuccess):
                return str(result.absolute_path)
            return None

        if isinstance(value, FileLocation):
            return str(value)

        return None

    def get_file_location(self, **extra_variables: str | int) -> FileLocation:
        """Get FileLocation from parameter value with node_name auto-populated.

        Args:
            **extra_variables: Additional variables for macro resolution (e.g., index=0)

        Returns:
            FileLocation instance ready for save/load operations

        Raises:
            ValueError: If parameter value is None or empty
            TypeError: If parameter value is unsupported type

        Example:
            >>> file_location = self._file_path_param.get_file_location()
            >>> file_location = self._file_path_param.get_file_location(index=0)
        """
        value = self._node.get_parameter_value(self._name)
        base_variables = {"node_name": self._node.name, **extra_variables}
        return FileLocation.from_any(value, base_variables=base_variables)

    def save(self, data: bytes, **extra_variables: str | int) -> str:
        """Save data using the parameter's file location.

        Automatically includes node_name in base_variables.

        Args:
            data: Binary data to save
            **extra_variables: Additional variables for macro resolution (e.g., index=0)

        Returns:
            URL of the saved file for UI display

        Raises:
            FileExistsError: If file exists and policy is FAIL
            RuntimeError: If save operation fails or macro resolution fails

        Example:
            >>> static_url = self._file_path_param.save(image_bytes)
            >>> static_url = self._file_path_param.save(image_bytes, index=i)
        """
        file_location = self.get_file_location(**extra_variables)
        return file_location.save(data)

    def load(self, timeout: float = 120.0) -> bytes:
        """Load data from the parameter's file location (synchronous).

        WARNING: This method makes synchronous HTTP requests which will block.
        For async contexts (node process methods), use aload() instead.

        Args:
            timeout: Timeout in seconds for HTTP downloads (default: 120.0)

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file does not exist at resolved path
            RuntimeError: If load operation fails or macro resolution fails

        Example:
            >>> image_bytes = self._file_path_param.load()
        """
        file_location = self.get_file_location()
        return file_location.load(timeout=timeout)

    async def aload(self, timeout: float = 120.0) -> bytes:  # noqa: ASYNC109
        """Load data from the parameter's file location (asynchronous).

        Use this in async contexts like node process methods to avoid blocking.

        Args:
            timeout: Timeout in seconds for HTTP downloads (default: 120.0)

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file does not exist at resolved path
            RuntimeError: If load operation fails or macro resolution fails

        Example:
            >>> image_bytes = await self._file_path_param.aload()
        """
        file_location = self.get_file_location()
        return await file_location.aload(timeout=timeout)
