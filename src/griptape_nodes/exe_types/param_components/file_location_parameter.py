"""FileLocationParameter - parameter component for file location UI integration."""

import logging
from typing import Any

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.file_location import FileLocation
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.parameter_events import GetConnectionsForParameterResultSuccess
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
    GetSituationRequest,
    GetSituationResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker

logger = logging.getLogger("griptape_nodes")


class FileLocationParameter:
    """Parameter component for FileLocation UI integration.

    This component provides:
    - Parameter creation with proper traits (FileSystemPicker, Button)
    - UI helper text updates showing resolved path preview
    - Button to create/connect ResolveFilePath nodes
    - Simple API for getting FileLocation objects for saving

    Usage:
        >>> # In node __init__:
        >>> self._file_path_param = FileLocationParameter(
        ...     node=self,
        ...     name="file_path",
        ...     situation_name="save_node_output",
        ...     filename="output.png",
        ... )
        >>> self._file_path_param.add_parameter()
        >>>
        >>> # In node process() - get FileLocation and save:
        >>> file_location = self._file_path_param.get_file_location()
        >>> static_url = file_location.save(data)
        >>>
        >>> # With extra variables (e.g., for multiple images):
        >>> file_location = self._file_path_param.get_file_location(image_index=i)
        >>> static_url = file_location.save(data)
    """

    def __init__(
        self,
        node: BaseNode,
        name: str,
        *,
        situation_name: str,
        allowed_modes: set[ParameterMode] | None = None,
        tooltip: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize FileLocationParameter component.

        Args:
            node: Parent node instance
            name: Parameter name
            situation_name: Name of the situation template (e.g., "save_node_output")
            allowed_modes: Set of allowed parameter modes (default: INPUT, PROPERTY)
            tooltip: Tooltip text for UI
            **kwargs: Additional parameter options (input_types, output_type, ui_options)
        """
        self._node = node
        self._name = name
        self._situation_name = situation_name
        self._tooltip = tooltip
        self._allowed_modes = allowed_modes or {ParameterMode.INPUT, ParameterMode.PROPERTY}
        self._input_types = kwargs.get("input_types") or ["FileLocation", "str"]
        self._output_type = kwargs.get("output_type") or "str"
        self._ui_options = kwargs.get("ui_options") or {}
        self._parameter: Parameter | None = None

        # Get default filename from kwargs or use generic default
        filename = kwargs.get("filename") or "output.png"

        # Fetch situation config
        config = self._fetch_situation_config(situation_name)
        if config:
            macro_template, file_policy, create_dirs = config
            self._situation_macro = macro_template
            self._default_value = filename
            self._existing_file_policy = file_policy
            self._create_parent_dirs = create_dirs
        else:
            logger.error("%s: Failed to load situation '%s', using fallback", self._node.name, situation_name)
            self._situation_macro = "{outputs}/{file_name_base}{_index?:03}.{file_extension}"
            self._default_value = filename
            self._existing_file_policy = ExistingFilePolicy.CREATE_NEW
            self._create_parent_dirs = True

    def get_situation_macro(self) -> str:
        """Get the situation macro template for use in FileLocation.from_value calls.

        Returns:
            The situation macro template string
        """
        return self._situation_macro

    def get_base_variables(self, **extra_variables: str | int) -> dict[str, str | int]:
        """Get base variables for FileLocation.from_value including parsed filename.

        Parses the current parameter value to extract file_name_base and file_extension,
        then merges with extra variables provided by the caller.

        Args:
            **extra_variables: Additional variables to merge (e.g., image_index, generation_id)

        Returns:
            Dictionary of variables ready for FileLocation.from_value
        """
        # Get the current parameter value
        value = self._node.get_parameter_value(self._name)
        if not value or not isinstance(value, str):
            value = self._default_value

        # Parse the simple filename to extract file_name_base and file_extension
        file_name_base, file_extension = self._parse_simple_filename(value)

        # Build base variables
        variables: dict[str, str | int] = {
            "node_name": self._node.name,
            "file_name_base": file_name_base,
            "file_extension": file_extension,
        }

        # Merge extra variables (caller's variables take precedence)
        variables.update(extra_variables)

        return variables

    def get_file_location(self, **extra_variables: str | int) -> FileLocation:
        """Get a FileLocation ready for saving files.

        This is the recommended way for nodes to get a FileLocation for saving.
        Handles both simple filenames and FileLocation objects from connections.

        Args:
            **extra_variables: Additional variables to merge (e.g., image_index, generation_id)

        Returns:
            FileLocation configured with situation macro, variables, and policies

        Example:
            >>> # In node process() method:
            >>> file_location = self._file_path_param.get_file_location(image_index=i)
            >>> url = file_location.save(image_bytes)
        """
        # Get the current parameter value
        value = self._node.get_parameter_value(self._name)

        # If value is already a FileLocation (from connection), return it
        if isinstance(value, FileLocation):
            # FileLocation from connection already has all configuration
            # Extra variables are ignored in this case
            return value

        # Otherwise, build FileLocation from situation macro
        base_variables = self.get_base_variables(**extra_variables)

        return FileLocation(
            macro_template=self._situation_macro,
            base_variables=base_variables,
            existing_file_policy=self._existing_file_policy,
            create_parent_dirs=self._create_parent_dirs,
        )

    def _fetch_situation_config(self, situation_name: str) -> tuple[str, Any, bool] | None:
        """Fetch situation and return (macro_template, existing_file_policy, create_parent_dirs).

        Args:
            situation_name: Name of situation to fetch

        Returns:
            Tuple of (macro_template, existing_file_policy, create_parent_dirs), or None if fetch fails
        """
        request = GetSituationRequest(situation_name=situation_name)
        result = GriptapeNodes.ProjectManager().on_get_situation_request(request)

        if not isinstance(result, GetSituationResultSuccess):
            logger.warning("%s: Failed to fetch situation '%s', using fallback", self._node.name, situation_name)
            return None

        situation = result.situation

        # Map SituationFilePolicy to ExistingFilePolicy
        policy_mapping = {
            SituationFilePolicy.CREATE_NEW: ExistingFilePolicy.CREATE_NEW,
            SituationFilePolicy.OVERWRITE: ExistingFilePolicy.OVERWRITE,
            SituationFilePolicy.FAIL: ExistingFilePolicy.FAIL,
        }

        existing_file_policy = policy_mapping.get(situation.policy.on_collision, ExistingFilePolicy.OVERWRITE)

        return (
            situation.macro,
            existing_file_policy,
            situation.policy.create_dirs,
        )

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

        # Use ui_options as-is
        ui_options = self._ui_options.copy()

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
            ui_options=ui_options,
        )

        self._node.add_parameter(self._parameter)

        # Hook into node's after_incoming_connection_removed to reset value automatically
        self._wrap_connection_removed_callback()

    def _wrap_connection_removed_callback(self) -> None:
        """Wrap the node's after_incoming_connection_removed to automatically reset parameter."""
        original_callback = self._node.after_incoming_connection_removed

        def wrapped_callback(source_node: BaseNode, source_parameter: Parameter, target_parameter: Parameter) -> None:
            # Call original callback first
            result = original_callback(source_node, source_parameter, target_parameter)

            # If our parameter had connection removed, reset to simple default
            if target_parameter.name == self._name:
                self._node.set_parameter_value(self._name, self._default_value)

            return result

        # Replace the node's method with our wrapped version
        self._node.after_incoming_connection_removed = wrapped_callback  # type: ignore[method-assign]

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
        """Compute what the resolved path would be (simple macro resolution).

        If a FileLocation object is provided (from a connection), uses that directly.
        Otherwise, parses the simple filename value and uses the situation macro.
        Shows the template resolved with variables, without collision detection.

        Returns:
            Resolved absolute path string, or None if resolution fails
        """
        if not hasattr(self, "_situation_macro"):
            return None

        # Get the current parameter value
        value = self._node.get_parameter_value(self._name) if self._parameter else None

        # Determine macro template and variables
        if isinstance(value, FileLocation):
            # Use the FileLocation's configuration (from connection)
            macro_template = value.macro_template
            variables: dict[str, str | int] = dict(value.base_variables)  # Ensure correct type
        else:
            # Parse simple filename and use situation macro
            if not value or not isinstance(value, str):
                value = self._default_value

            file_name_base, file_extension = self._parse_simple_filename(value)
            macro_template = self._situation_macro
            variables: dict[str, str | int] = {
                "node_name": self._node.name,
                "file_name_base": file_name_base,
                "file_extension": file_extension,
            }

        # Simple macro resolution (no collision detection)
        parsed_macro = ParsedMacro(macro_template)
        resolve_request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables=variables)
        result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(resolve_request)

        if isinstance(result, GetPathForMacroResultSuccess):
            return str(result.absolute_path)

        return None

    def _parse_simple_filename(self, filename: str) -> tuple[str, str]:
        """Parse a simple filename into file_name_base and file_extension.

        Args:
            filename: Simple filename like "output.png" or "my_image.jpg"

        Returns:
            Tuple of (file_name_base, file_extension)
        """
        if "." in filename:
            parts = filename.rsplit(".", 1)
            return parts[0], parts[1]
        return filename, "png"
