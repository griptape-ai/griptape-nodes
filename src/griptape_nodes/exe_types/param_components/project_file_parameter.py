"""ProjectFileParameter - parameter component for project-aware file saving."""

import logging
from typing import Any

from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.project import (
    ExistingFilePolicy,
    Project,
    ProjectFileSaveConfig,
    SaveRequest,
    SaveResult,
)
from griptape_nodes.retained_mode.events.parameter_events import GetConnectionsForParameterResultSuccess
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationRequest,
    GetSituationResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker

logger = logging.getLogger("griptape_nodes")


class ProjectFileParameter:
    """Parameter component for project-aware file saving.

    Responsibilities:
    - Fetch situation configuration
    - Create parameter with FileSystemPicker trait
    - Parse user's filename input
    - Build SaveRequest with macro, variables, and policy

    Does NOT:
    - Perform any file I/O
    - Resolve macros (that's Project)
    - Handle collisions (that's Project)

    Usage:
        >>> # In node __init__:
        >>> self._file_param = ProjectFileParameter(
        ...     node=self,
        ...     name="output_file",
        ...     situation="save_node_output",
        ...     default_filename="image.png",
        ... )
        >>> self._file_param.add_parameter()
        >>>
        >>> # In node process() - simple save:
        >>> result = self._file_param.save(data=image_bytes)
        >>>
        >>> # With extra variables (e.g., for multiple images):
        >>> result = self._file_param.save(
        ...     data=image_bytes,
        ...     image_index=i,
        ...     generation_id=gen_id
        ... )
    """

    def __init__(
        self,
        node: BaseNode,
        name: str,
        situation: str,
        *,
        default_filename: str = "output.png",
        allowed_modes: set[ParameterMode] | None = None,
    ) -> None:
        """Initialize with situation context.

        Args:
            node: Parent node instance
            name: Parameter name
            situation: Situation name (e.g., "save_node_output")
            default_filename: Default filename if parameter is empty
            allowed_modes: Set of allowed parameter modes (default: INPUT, PROPERTY)
        """
        self._node = node
        self._name = name
        self._situation_name = situation
        self._default_filename = default_filename
        self._allowed_modes = allowed_modes or {ParameterMode.INPUT, ParameterMode.PROPERTY}

        # Fetch situation configuration
        config = self._fetch_situation_config(situation)
        if config:
            macro_template, policy, create_dirs = config
            self._macro_template = macro_template
            self._policy = policy
            self._create_dirs = create_dirs
        else:
            # Fallback configuration
            logger.error("%s: Failed to load situation '%s', using fallback configuration", self._node.name, situation)
            self._macro_template = "{outputs}/{node_name}_{file_name_base}{_index?:03}.{file_extension}"
            self._policy = ExistingFilePolicy.CREATE_NEW
            self._create_dirs = True

    def add_parameter(self) -> None:
        """Create and add parameter to node with FileSystemPicker trait."""
        # Generate tooltip
        tooltip = f"Filename (uses '{self._situation_name}' situation)"

        # Build traits set
        traits: set = {
            FileSystemPicker(
                allow_files=True,
                allow_directories=False,
                allow_create=True,
            )
        }

        # Add button if parameter accepts input connections
        if ParameterMode.INPUT in self._allowed_modes:
            traits.add(
                Button(
                    icon="cog",
                    size="icon",
                    variant="secondary",
                    position="before",
                    tooltip="Create and connect a ConfigureProjectFileSave node",
                    on_click=lambda button, button_details: self._create_configure_node_callback(
                        button, button_details
                    ),
                )
            )

        # Custom converter that handles both ProjectFileSaveConfig and string inputs
        def _normalize_file_path_input(value: Any) -> Any:
            """Normalize file path input - preserve ProjectFileSaveConfig, convert others to string."""
            if value is None:
                return None
            if isinstance(value, ProjectFileSaveConfig):
                return value
            return str(value)

        # Create parameter - use generic Parameter (not ParameterString) to avoid auto-stringification
        parameter = Parameter(
            name=self._name,
            type="str",
            default_value=self._default_filename,
            allowed_modes=self._allowed_modes,
            tooltip=tooltip,
            input_types=["ProjectFileSaveConfig", "str"],
            output_type="str",
            traits=traits,
            converters=[_normalize_file_path_input],
        )

        self._node.add_parameter(parameter)

    def create_save_request(self, data: bytes, **extra_vars: str | int) -> SaveRequest:
        """Build SaveRequest for Project.

        Args:
            data: Bytes to save
            **extra_vars: Additional variables (e.g., image_index=0, generation_id=123)

        Returns:
            SaveRequest with situation's macro, variables, and policy
        """
        # Get parameter value
        value = self._node.get_parameter_value(self._name)

        # Check if value is a ProjectFileSaveConfig from ConfigureProjectFileSave node
        if isinstance(value, ProjectFileSaveConfig):
            # Use custom configuration from ConfigureProjectFileSave
            macro_template = value.macro_template
            policy = value.policy
            create_dirs = value.create_dirs

            # If ConfigureProjectFileSave provided variables, use those
            if value.variables:
                variables = {**value.variables, **extra_vars}
            else:
                # Fallback: create variables from filename
                filename = str(extra_vars.get("file_name_base", self._default_filename))
                file_name_base, file_extension = self._parse_filename(filename)
                variables = {
                    "file_name_base": file_name_base,
                    "file_extension": file_extension,
                    "node_name": self._node.name,
                    **extra_vars,
                }
        else:
            # Use situation configuration and create variables
            macro_template = self._macro_template
            policy = self._policy
            create_dirs = self._create_dirs

            # Get filename from parameter or use default
            if value and isinstance(value, str):
                filename = value
            else:
                filename = self._default_filename

            # Parse filename into variables
            file_name_base, file_extension = self._parse_filename(filename)

            # Build complete variables dict
            variables = {
                "file_name_base": file_name_base,
                "file_extension": file_extension,
                "node_name": self._node.name,
                **extra_vars,
            }

        # Return SaveRequest with configuration
        return SaveRequest(
            data=data,
            macro_template=macro_template,
            variables=variables,
            policy=policy,
            create_dirs=create_dirs,
        )

    def save(self, data: bytes, **extra_vars: str | int) -> SaveResult:
        """Build SaveRequest and save to project.

        Convenience method that combines create_save_request() and Project.save().

        Args:
            data: Bytes to save
            **extra_vars: Additional variables (e.g., image_index=0, generation_id=123)

        Returns:
            SaveResult with path and metadata
        """
        request = self.create_save_request(data=data, **extra_vars)
        project = Project()
        return project.save(request)

    def _fetch_situation_config(self, situation_name: str) -> tuple[str, ExistingFilePolicy, bool] | None:
        """Fetch situation and return (macro_template, policy, create_dirs).

        Args:
            situation_name: Name of situation to fetch

        Returns:
            Tuple of configuration, or None if fetch fails
        """
        request = GetSituationRequest(situation_name=situation_name)
        result = GriptapeNodes.ProjectManager().on_get_situation_request(request)

        if not isinstance(result, GetSituationResultSuccess):
            logger.warning("%s: Failed to fetch situation '%s'", self._node.name, situation_name)
            return None

        situation = result.situation

        # Map policy from situation to ExistingFilePolicy
        from griptape_nodes.common.project_templates.situation import SituationFilePolicy

        policy_mapping = {
            SituationFilePolicy.CREATE_NEW: ExistingFilePolicy.CREATE_NEW,
            SituationFilePolicy.OVERWRITE: ExistingFilePolicy.OVERWRITE,
            SituationFilePolicy.FAIL: ExistingFilePolicy.FAIL,
        }

        policy = policy_mapping.get(situation.policy.on_collision, ExistingFilePolicy.CREATE_NEW)
        create_dirs = situation.policy.create_dirs

        return situation.macro, policy, create_dirs

    def _parse_filename(self, filename: str) -> tuple[str, str]:
        """Parse filename into base and extension.

        Examples:
        - "image.png" → ("image", "png")
        - "output.tar.gz" → ("output.tar", "gz")
        - "test" → ("test", "png")  # default extension from self._default_filename

        Args:
            filename: Filename to parse

        Returns:
            Tuple of (base, extension)
        """
        if "." in filename:
            parts = filename.rsplit(".", 1)
            return parts[0], parts[1]

        # No extension - use default extension from default_filename
        if "." in self._default_filename:
            default_parts = self._default_filename.rsplit(".", 1)
            return filename, default_parts[1]

        return filename, "png"  # Ultimate fallback

    def _create_configure_node_callback(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Create and connect a ConfigureProjectFileSave node to this parameter."""
        node_name = self._node.name
        if not node_name:
            return NodeMessageResult(
                success=False,
                details="Cannot create configure node: node has no name",
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

        # Create ConfigureProjectFileSave node positioned to the left
        create_result = RetainedMode.create_node_relative_to(
            reference_node_name=node_name,
            new_node_type="ConfigureProjectFileSave",
            offset_side="left",
            offset_x=-750,
            offset_y=0,
            lock=False,
        )

        if not isinstance(create_result, str):
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to create ConfigureProjectFileSave node",
                response=button_details,
                altered_workflow_state=False,
            )

        configure_node_name = create_result

        # Connect ConfigureProjectFileSave.file_location to this parameter
        connection_result = RetainedMode.connect(
            source=f"{configure_node_name}.file_location", destination=f"{node_name}.{self._name}"
        )

        if not connection_result.succeeded():
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to connect {configure_node_name}.file_location to {self._name}",
                response=button_details,
                altered_workflow_state=True,
            )

        return NodeMessageResult(
            success=True,
            details=f"{node_name}: Created and connected {configure_node_name}",
            response=button_details,
            altered_workflow_state=True,
        )
