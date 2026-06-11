"""ProjectDirectoryParameter - parameter component for project-aware directory creation.

Provisions a versioned output directory via situation-based macro routing and exposes it as a
DirectoryDestination. Falls back to a sensible default when no situation is configured.
"""

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.project_output_parameter import ProjectOutputParameter
from griptape_nodes.files.directory import DirectoryDestination
from griptape_nodes.files.project_file import resolve_situation
from griptape_nodes.retained_mode.events.project_events import MacroPath
from griptape_nodes.traits.file_system_picker import FileSystemPicker

_FALLBACK_DIRECTORY_MACRO = "{outputs}/{node_name?:_}{dir_name}_v{_index:03}"


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

        If an upstream node exposes a ``directory_destination`` attribute, its
        ``DirectoryDestination`` is retrieved directly. Otherwise the parameter's
        string value is used as the directory name, combined with the situation macro.

        Args:
            **extra_vars: Additional variables for the macro (e.g., sub_dirs="renders")

        Returns:
            DirectoryDestination with a versioned MacroPath and baked-in policy.

        Raises:
            ValueError: If an upstream node exposes ``directory_destination`` but returns None.
        """
        upstream = self._get_upstream_destination("directory_destination", "DirectoryDestination")
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
    resolved = resolve_situation(situation, _FALLBACK_DIRECTORY_MACRO)
    variables: dict[str, str | int] = {
        "dir_name": dirname,
        **extra_vars,
    }
    macro_path = MacroPath(ParsedMacro(resolved.macro_template), variables)
    return DirectoryDestination(
        macro_path,
        existing_dir_policy=resolved.existing_file_policy,
        create_parents=resolved.create_parents,
    )
