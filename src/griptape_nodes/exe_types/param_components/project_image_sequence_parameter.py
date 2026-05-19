"""ProjectImageSequenceParameter - parameter component for project-aware image sequence output."""

import logging

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.files.image_sequence import (
    ImageSequenceDestination,
    build_versioned_sequence_destination,
    hash_pattern_to_frame_macro,
)
from griptape_nodes.files.path_utils import FilenameParts
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

logger = logging.getLogger("griptape_nodes")

_FALLBACK_SEQUENCE_MACRO = (
    "{outputs}/{node_name?:_}{file_name_base}_v{_index:03}/{file_name_base}_v{_index:03}_{frame:04}.{file_extension}"
)


class ImageSequenceDestinationProvider:
    """Protocol for nodes that provide an ImageSequenceDestination without serializing it over the wire."""

    @property
    def image_sequence_destination(self) -> ImageSequenceDestination | None: ...


class ProjectImageSequenceParameter:
    """Parameter component for project-aware image sequence output.

    Adds a filename-pattern parameter to a node that, when processed, returns an
    ``ImageSequenceDestination`` with a versioned macro path for deferred resolution.

    The parameter accepts a filename like ``"frame.exr"`` or a ``####`` pattern
    like ``"frame_####.exr"``. The situation macro wraps it with versioning.

    Usage:
        # In node __init__:
        self._seq_param = ProjectImageSequenceParameter(
            node=self,
            name="output_sequence",
            default_filename="frame.exr",
        )
        self._seq_param.add_parameter()

        # In node process():
        dest = self._seq_param.build_sequence()
        for i, frame_data in enumerate(frames):
            dest.frame(i + 1).write_bytes(frame_data)
        seq = dest.image_sequence
        if seq is not None:
            self.set_parameter_value("output_sequence", seq.location)
    """

    DEFAULT_SITUATION = "save_image_sequence_frame"

    def __init__(  # noqa: PLR0913
        self,
        node: BaseNode,
        name: str,
        *,
        default_filename: str,
        situation: str = DEFAULT_SITUATION,
        allowed_modes: set[ParameterMode] | None = None,
        ui_options: dict | None = None,
    ) -> None:
        """Initialize with situation context.

        Args:
            node: Parent node instance
            name: Parameter name
            default_filename: Default filename (e.g., ``"frame.exr"`` or ``"frame_####.exr"``)
            situation: Situation name (default: "save_image_sequence_frame")
            allowed_modes: Set of allowed parameter modes (default: INPUT, PROPERTY)
            ui_options: Optional UI options to pass to the generated parameter
        """
        self._node = node
        self._name = name
        self._situation_name = situation
        self._default_filename = default_filename
        self._allowed_modes = allowed_modes or {ParameterMode.INPUT, ParameterMode.PROPERTY}
        self._ui_options = ui_options

    def add_parameter(self) -> None:
        """Create and add the image sequence pattern parameter to the node."""
        tooltip = f"Output frame filename (uses '{self._situation_name}' situation template)"

        traits: set = set()

        if ParameterMode.INPUT in self._allowed_modes:
            traits.add(
                Button(
                    icon="cog",
                    size="icon",
                    variant="secondary",
                    tooltip="Create and connect an ImageSequenceSettings node",
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
            output_type="ImageSequence",
            traits=traits,
            ui_options=self._ui_options,
        )
        parameter.on_incoming_connection_removed.append(self._reset_to_default)

        self._node.add_parameter(parameter)

    def build_sequence(self, **extra_vars: str | int) -> ImageSequenceDestination:
        """Build an ImageSequenceDestination from the parameter's current value.

        If an upstream node implements ImageSequenceDestinationProvider, its
        ImageSequenceDestination is retrieved directly. Otherwise the parameter's
        string value (filename or #### pattern) is parsed and combined with the
        situation macro.

        Args:
            **extra_vars: Additional variables for the macro (e.g., sub_dirs="renders")

        Returns:
            ImageSequenceDestination with a versioned MacroPath and baked-in policy.

        Raises:
            ValueError: If an upstream ImageSequenceDestinationProvider returns None.
            ImageSequenceError: If no available version index can be found.
        """
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self._node.name))
        if isinstance(result, ListConnectionsForNodeResultSuccess):
            for conn in result.incoming_connections:
                if conn.target_parameter_name == self._name:
                    source_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name(conn.source_node_name)
                    if isinstance(source_node, ImageSequenceDestinationProvider):
                        seq_dest = source_node.image_sequence_destination
                        if seq_dest is None:
                            msg = (
                                f"Attempted to build image sequence destination for {self._node.name}.{self._name}. "
                                f"Failed because upstream node '{conn.source_node_name}' provides an "
                                f"ImageSequenceDestination but returned None (likely missing a filename)."
                            )
                            raise ValueError(msg)
                        return seq_dest

        value = self._node.get_parameter_value(self._name)
        filename = value if isinstance(value, str) and value else self._default_filename

        if "node_name" not in extra_vars:
            extra_vars["node_name"] = self._node.name

        return _build_sequence_destination_from_situation(filename, self._situation_name, **extra_vars)

    def _reset_to_default(
        self,
        parameter: Parameter,  # noqa: ARG002
        source_node_name: str,  # noqa: ARG002
        source_parameter_name: str,  # noqa: ARG002
    ) -> None:
        self._node.set_parameter_value(self._name, self._default_filename)
        self._node.publish_update_to_parameter(self._name, self._default_filename)

    def _on_configure_button_clicked(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Create and connect an ImageSequenceSettings node to this parameter."""
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
            new_node_type="ImageSequenceSettings",
            offset_side="left",
            offset_x=-750,
            offset_y=0,
            lock=False,
        )

        if not isinstance(create_result, str):
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to create ImageSequenceSettings node",
                response=button_details,
                altered_workflow_state=False,
            )

        configure_node_name = create_result

        configure_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name(configure_node_name)
        if configure_node is not None:
            configure_node.set_parameter_value("situation", self._situation_name)
            configure_node.publish_update_to_parameter("situation", self._situation_name)

            current_filename = self._node.get_parameter_value(self._name)
            if isinstance(current_filename, str) and current_filename:
                configure_node.set_parameter_value("filename", current_filename)
                configure_node.publish_update_to_parameter("filename", current_filename)

        connection_result = RetainedMode.connect(
            source=f"{configure_node_name}.sequence_destination",
            destination=f"{node_name}.{self._name}",
        )

        if not connection_result.succeeded():
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to connect {configure_node_name}.sequence_destination to {self._name}",
                response=button_details,
                altered_workflow_state=True,
            )

        return NodeMessageResult(
            success=True,
            details=f"{node_name}: Created and connected {configure_node_name}",
            response=button_details,
            altered_workflow_state=True,
        )


def _build_sequence_destination_from_situation(
    filename: str,
    situation: str,
    **extra_vars: str | int,
) -> ImageSequenceDestination:
    """Build an ImageSequenceDestination from a project situation template.

    Parses the filename (or #### pattern) into parts, looks up the situation,
    and builds a versioned destination by finding the first available ``_index``.

    Args:
        filename: Filename or #### pattern (e.g., ``"frame.exr"`` or ``"frame_####.exr"``).
        situation: Situation name to look up in the current project.
        **extra_vars: Additional macro variables.

    Returns:
        ImageSequenceDestination with a locked version index.
    """
    situation_result = GriptapeNodes.handle_request(GetSituationRequest(situation_name=situation))

    if isinstance(situation_result, GetSituationResultSuccess):
        situation_obj = situation_result.situation
        macro_template = situation_obj.macro
        on_collision = situation_obj.policy.on_collision
        existing_file_policy = SITUATION_TO_FILE_POLICY.get(on_collision, ExistingFilePolicy.OVERWRITE)
        create_parents = situation_obj.policy.create_dirs
    else:
        logger.error("Failed to load situation '%s', using fallback sequence macro template", situation)
        macro_template = _FALLBACK_SEQUENCE_MACRO
        existing_file_policy = ExistingFilePolicy.OVERWRITE
        create_parents = True

    normalized_filename = hash_pattern_to_frame_macro(filename)
    parts = FilenameParts.from_filename(normalized_filename)

    variables: dict[str, str | int] = {
        "file_name_base": parts.stem,
        "file_extension": parts.extension,
        **extra_vars,
    }

    macro_path = MacroPath(ParsedMacro(macro_template), variables)
    return build_versioned_sequence_destination(
        macro_path,
        existing_file_policy=existing_file_policy,
        create_parents=create_parents,
    )
