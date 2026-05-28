"""ProjectImageSequenceParameter - parameter component for project-aware image sequence output."""

import logging

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.project_output_parameter import ProjectOutputParameter
from griptape_nodes.files.image_sequence import (
    ImageSequenceDestination,
    build_versioned_sequence_destination,
    hash_pattern_to_frame_macro,
)
from griptape_nodes.files.path_utils import FilenameParts
from griptape_nodes.files.project_file import SITUATION_TO_FILE_POLICY
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationRequest,
    GetSituationResultSuccess,
    MacroPath,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")

_FALLBACK_SEQUENCE_MACRO = (
    "{outputs}/{node_name?:_}{file_name_base}_v{_index:03}/{file_name_base}_v{_index:03}_{frame:04}.{file_extension}"
)


class ImageSequenceDestinationProvider:
    """Protocol for nodes that provide an ImageSequenceDestination without serializing it over the wire."""

    @property
    def image_sequence_destination(self) -> ImageSequenceDestination | None: ...


class ProjectImageSequenceParameter(ProjectOutputParameter):
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
        super().__init__(
            node,
            name,
            default_value=default_filename,
            situation=situation,
            allowed_modes=allowed_modes,
            ui_options=ui_options,
        )

    @property
    def _settings_node_type(self) -> str:
        return "ImageSequenceSettings"

    @property
    def _settings_value_param_name(self) -> str:
        return "filename"

    @property
    def _settings_source_param_name(self) -> str:
        return "sequence_destination"

    @property
    def _parameter_output_type(self) -> str:
        return "ImageSequence"

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
        upstream = self._get_upstream_destination(
            ImageSequenceDestinationProvider, "image_sequence_destination", "ImageSequenceDestination"
        )
        if upstream is not None:
            return upstream  # type: ignore[return-value]

        value = self._node.get_parameter_value(self._name)
        filename = value if isinstance(value, str) and value else self._default_value

        if "node_name" not in extra_vars:
            extra_vars["node_name"] = self._node.name

        return _build_sequence_destination_from_situation(filename, self._situation_name, **extra_vars)


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
