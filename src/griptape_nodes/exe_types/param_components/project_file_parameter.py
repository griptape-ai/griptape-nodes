"""ProjectFileParameter - parameter component for project-aware file saving."""

import logging

from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.files.file import FileDestination, FileDestinationProvider
from griptape_nodes.files.path_utils import parse_filename_components
from griptape_nodes.files.situation_file_builder import (
    SituationConfig,
    build_file_from_situation,
    fetch_situation_config,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    GetConnectionsForParameterRequest,
    GetConnectionsForParameterResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker

logger = logging.getLogger("griptape_nodes")


class ProjectFileParameter:
    """Parameter component for project-aware file saving.

    Adds a file path parameter to a node that, when processed, returns a
    FileDestination containing a MacroPath and baked-in write policy for
    deferred path resolution.

    Usage:
        # In node __init__:
        self._file_param = ProjectFileParameter(
            node=self,
            name="output_file",
            situation="save_node_output",
            default_filename="image.png",
        )
        self._file_param.add_parameter()

        # In node process():
        output_file = self._file_param.build_file(sub_dirs="renders")
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

        # Fetch situation's macro template and policy directly via GetSituationRequest
        self._situation_config: SituationConfig = fetch_situation_config(situation, node.name)

    def add_parameter(self) -> None:
        """Create and add the file path parameter to the node."""
        tooltip = f"Output filename (uses '{self._situation_name}' situation template)"

        traits: set = {
            FileSystemPicker(
                allow_files=True,
                allow_directories=False,
                allow_create=True,
            )
        }

        if ParameterMode.INPUT in self._allowed_modes:
            traits.add(
                Button(
                    icon="cog",
                    size="icon",
                    variant="secondary",
                    tooltip="Create and connect a ConfigureProjectFileSave node",
                    on_click=self._on_configure_button_clicked,
                )
            )

        parameter = Parameter(
            name=self._name,
            type="str",
            default_value=self._default_filename,
            allowed_modes=self._allowed_modes,
            tooltip=tooltip,
            input_types=["str"],
            output_type="str",
            traits=traits,
        )

        self._node.add_parameter(parameter)

    def build_file(self, **extra_vars: str | int) -> FileDestination:
        """Build a FileDestination with a MacroPath from the parameter's current value.

        If an upstream node implements FileDestinationProvider (e.g., ConfigureProjectFileSave),
        its FileDestination is retrieved directly without deserializing from the wire.

        If the parameter holds a string filename, parses it into
        file_name_base/file_extension, builds a MacroPath using the
        situation's macro template, and wraps it in a FileDestination.

        Args:
            **extra_vars: Additional variables for the macro (e.g., sub_dirs="renders")

        Returns:
            FileDestination with a MacroPath and baked-in write policy for deferred path resolution
        """
        connections_result = GriptapeNodes.handle_request(
            GetConnectionsForParameterRequest(parameter_name=self._name, node_name=self._node.name)
        )
        if isinstance(connections_result, GetConnectionsForParameterResultSuccess):
            for connection in connections_result.incoming_connections:
                upstream_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name(connection.source_node_name)
                if isinstance(upstream_node, FileDestinationProvider):
                    file_dest = upstream_node.file_destination
                    if file_dest is not None:
                        return file_dest

        value = self._node.get_parameter_value(self._name)

        if isinstance(value, str) and value:
            filename = value
        else:
            filename = self._default_filename

        default_extension = parse_filename_components(self._default_filename)[1]

        return build_file_from_situation(
            filename=filename,
            situation_config=self._situation_config,
            node_name=self._node.name,
            default_extension=default_extension,
            extra_variables=extra_vars if extra_vars else None,
        )

    def _on_configure_button_clicked(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Create and connect a ConfigureProjectFileSave node to this parameter."""
        node_name = self._node.name

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

        connection_result = RetainedMode.connect(
            source=f"{configure_node_name}.file_destination",
            destination=f"{node_name}.{self._name}",
        )

        if not connection_result.succeeded():
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to connect {configure_node_name}.file_destination to {self._name}",
                response=button_details,
                altered_workflow_state=True,
            )

        return NodeMessageResult(
            success=True,
            details=f"{node_name}: Created and connected {configure_node_name}",
            response=button_details,
            altered_workflow_state=True,
        )
