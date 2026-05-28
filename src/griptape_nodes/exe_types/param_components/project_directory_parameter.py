"""ProjectDirectoryParameter - parameter component for project-aware directory creation."""

import logging

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.project_output_parameter import ProjectOutputParameter
from griptape_nodes.files.directory import DirectoryDestination
from griptape_nodes.files.project_file import SITUATION_TO_FILE_POLICY
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationRequest,
    GetSituationResultSuccess,
    MacroPath,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker

logger = logging.getLogger("griptape_nodes")

_FALLBACK_DIRECTORY_MACRO = "{outputs}/{node_name?:_}{dir_name}_v{_index:03}"


class DirectoryDestinationProvider:
    """Protocol for nodes that provide a DirectoryDestination without serializing it over the wire."""

    @property
    def directory_destination(self) -> DirectoryDestination | None: ...


class ProjectDirectoryParameter(ProjectOutputParameter):
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
        super().__init__(
            node,
            name,
            default_value=default_dirname,
            situation=situation,
            allowed_modes=allowed_modes,
            ui_options=ui_options,
        )

    @property
    def _settings_node_type(self) -> str:
        return "DirectoryOutputSettings"

    @property
    def _settings_value_param_name(self) -> str:
        return "dirname"

    @property
    def _settings_source_param_name(self) -> str:
        return "directory_destination"

    @property
    def _parameter_output_type(self) -> str:
        return "Directory"

    def _make_parameter_traits(self) -> set:
        return {
            FileSystemPicker(
                allow_files=False,
                allow_directories=True,
                allow_create=True,
            )
        }

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
        upstream = self._get_upstream_destination(
            DirectoryDestinationProvider, "directory_destination", "DirectoryDestination"
        )
        if upstream is not None:
            return upstream  # type: ignore[return-value]

        value = self._node.get_parameter_value(self._name)
        dirname = value if isinstance(value, str) and value else self._default_value

        if "node_name" not in extra_vars:
            extra_vars["node_name"] = self._node.name

        return _build_directory_destination_from_situation(dirname, self._situation_name, **extra_vars)


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
