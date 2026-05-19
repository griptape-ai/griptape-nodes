"""ProjectDirectoryParameter - parameter component for project-aware directory creation."""

import logging

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.files.directory import DirectoryDestination
from griptape_nodes.files.project_file import SITUATION_TO_FILE_POLICY
from griptape_nodes.retained_mode.events.connection_events import (
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationRequest,
    GetSituationResultSuccess,
    MacroPath,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker

logger = logging.getLogger("griptape_nodes")

_FALLBACK_DIRECTORY_MACRO = "{outputs}/{node_name?:_}{dir_name}_v{_index:03}"


class DirectoryDestinationProvider:
    """Protocol for nodes that provide a DirectoryDestination without serializing it over the wire."""

    @property
    def directory_destination(self) -> DirectoryDestination | None: ...


class ProjectDirectoryParameter:
    """Parameter component for project-aware directory creation.

    Adds a directory name parameter to a node that, when processed, returns a
    ``DirectoryDestination`` with a versioned macro path for deferred resolution.

    Usage:
        # In node __init__:
        self._dir_param = ProjectDirectoryParameter(
            node=self,
            name="output_dir",
            default_dirname="renders",
        )
        self._dir_param.add_parameter()

        # In node process():
        dest = self._dir_param.build_directory()
        directory = dest.create()
        self.set_parameter_value("output_dir", directory.location)
    """

    DEFAULT_SITUATION = "save_output_directory"

    def __init__(  # noqa: PLR0913
        self,
        node: BaseNode,
        name: str,
        *,
        default_dirname: str,
        situation: str = DEFAULT_SITUATION,
        allowed_modes: set[ParameterMode] | None = None,
        ui_options: dict | None = None,
    ) -> None:
        """Initialize with situation context.

        Args:
            node: Parent node instance
            name: Parameter name
            default_dirname: Default directory name if parameter is empty
            situation: Situation name (default: "save_output_directory")
            allowed_modes: Set of allowed parameter modes (default: INPUT, PROPERTY)
            ui_options: Optional UI options to pass to the generated parameter
        """
        self._node = node
        self._name = name
        self._situation_name = situation
        self._default_dirname = default_dirname
        self._allowed_modes = allowed_modes or {ParameterMode.INPUT, ParameterMode.PROPERTY}
        self._ui_options = ui_options

    def add_parameter(self) -> None:
        """Create and add the directory name parameter to the node."""
        tooltip = f"Output directory name (uses '{self._situation_name}' situation template)"

        traits: set = {
            FileSystemPicker(
                allow_files=False,
                allow_directories=True,
                allow_create=True,
            )
        }

        if ParameterMode.INPUT in self._allowed_modes:
            traits.add(
                Button(
                    icon="cog",
                    size="icon",
                    variant="secondary",
                    tooltip="Create and connect a DirectoryOutputSettings node",
                    on_click=self._on_configure_button_clicked,
                )
            )

        parameter = Parameter(
            name=self._name,
            type="str",
            default_value=self._default_dirname,
            allowed_modes=self._allowed_modes,
            tooltip=tooltip,
            input_types=["str"],
            output_type="Directory",
            traits=traits,
            ui_options=self._ui_options,
        )
        parameter.on_incoming_connection_removed.append(self._reset_to_default)

        self._node.add_parameter(parameter)

    def build_directory(self, **extra_vars: str | int) -> DirectoryDestination:
        """Build a DirectoryDestination from the parameter's current value.

        If an upstream node implements DirectoryDestinationProvider, its
        DirectoryDestination is retrieved directly. Otherwise the parameter's
        string value is used as the directory name, combined with the situation
        macro.

        Args:
            **extra_vars: Additional variables for the macro (e.g., sub_dirs="renders")

        Returns:
            DirectoryDestination with a versioned MacroPath and baked-in policy.

        Raises:
            ValueError: If an upstream DirectoryDestinationProvider returns None.
        """
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self._node.name))
        if isinstance(result, ListConnectionsForNodeResultSuccess):
            for conn in result.incoming_connections:
                if conn.target_parameter_name == self._name:
                    source_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name(conn.source_node_name)
                    if isinstance(source_node, DirectoryDestinationProvider):
                        dir_dest = source_node.directory_destination
                        if dir_dest is None:
                            msg = (
                                f"Attempted to build directory destination for {self._node.name}.{self._name}. "
                                f"Failed because upstream node '{conn.source_node_name}' provides a "
                                f"DirectoryDestination but returned None (likely missing a directory name)."
                            )
                            raise ValueError(msg)
                        return dir_dest

        value = self._node.get_parameter_value(self._name)
        dirname = value if isinstance(value, str) and value else self._default_dirname

        if "node_name" not in extra_vars:
            extra_vars["node_name"] = self._node.name

        return _build_directory_destination_from_situation(dirname, self._situation_name, **extra_vars)

    def _reset_to_default(
        self,
        parameter: Parameter,  # noqa: ARG002
        source_node_name: str,  # noqa: ARG002
        source_parameter_name: str,  # noqa: ARG002
    ) -> None:
        self._node.set_parameter_value(self._name, self._default_dirname)
        self._node.publish_update_to_parameter(self._name, self._default_dirname)

    def _on_configure_button_clicked(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Create and connect a DirectoryOutputSettings node to this parameter."""
        node_name = self._node.name

        has_incoming = False
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=node_name))
        if isinstance(result, ListConnectionsForNodeResultSuccess):
            has_incoming = any(conn.target_parameter_name == self._name for conn in result.incoming_connections)

        if has_incoming:
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: {self._name} parameter already has an incoming connection",
                response=button_details,
                altered_workflow_state=False,
            )

        create_result = RetainedMode.create_node_relative_to(
            reference_node_name=node_name,
            new_node_type="DirectoryOutputSettings",
            offset_side="left",
            offset_x=-750,
            offset_y=0,
            lock=False,
        )

        if not isinstance(create_result, str):
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to create DirectoryOutputSettings node",
                response=button_details,
                altered_workflow_state=False,
            )

        configure_node_name = create_result

        configure_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name(configure_node_name)
        if configure_node is not None:
            configure_node.set_parameter_value("situation", self._situation_name)
            configure_node.publish_update_to_parameter("situation", self._situation_name)

            current_dirname = self._node.get_parameter_value(self._name)
            if isinstance(current_dirname, str) and current_dirname:
                configure_node.set_parameter_value("dirname", current_dirname)
                configure_node.publish_update_to_parameter("dirname", current_dirname)

        connection_result = RetainedMode.connect(
            source=f"{configure_node_name}.directory_destination",
            destination=f"{node_name}.{self._name}",
        )

        if not connection_result.succeeded():
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to connect {configure_node_name}.directory_destination to {self._name}",
                response=button_details,
                altered_workflow_state=True,
            )

        return NodeMessageResult(
            success=True,
            details=f"{node_name}: Created and connected {configure_node_name}",
            response=button_details,
            altered_workflow_state=True,
        )


def _build_directory_destination_from_situation(
    dirname: str,
    situation: str,
    **extra_vars: str | int,
) -> DirectoryDestination:
    """Build a DirectoryDestination from a project situation template.

    Args:
        dirname: Directory name to use as the ``dir_name`` macro variable.
        situation: Situation name to look up in the current project.
        **extra_vars: Additional macro variables.

    Returns:
        DirectoryDestination with a MacroPath and baked-in creation policy.
    """
    situation_result = GriptapeNodes.handle_request(GetSituationRequest(situation_name=situation))

    if isinstance(situation_result, GetSituationResultSuccess):
        situation_obj = situation_result.situation
        macro_template = situation_obj.macro
        on_collision = situation_obj.policy.on_collision
        existing_dir_policy = SITUATION_TO_FILE_POLICY.get(on_collision, ExistingFilePolicy.CREATE_NEW)
        create_parents = situation_obj.policy.create_dirs
    else:
        logger.error("Failed to load situation '%s', using fallback directory macro template", situation)
        macro_template = _FALLBACK_DIRECTORY_MACRO
        existing_dir_policy = ExistingFilePolicy.CREATE_NEW
        create_parents = True

    variables: dict[str, str | int] = {
        "dir_name": dirname,
        **extra_vars,
    }

    macro_path = MacroPath(ParsedMacro(macro_template), variables)
    return DirectoryDestination(
        macro_path,
        existing_dir_policy=existing_dir_policy,
        create_parents=create_parents,
    )
