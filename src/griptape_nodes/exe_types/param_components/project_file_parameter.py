"""ProjectFileParameter - parameter component for project-aware file saving."""

import logging

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.project import (
    ExistingFilePolicy,
    ProjectFileSaveConfig,
    SaveRequest,
)
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationRequest,
    GetSituationResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
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
        >>> # In node process() - create save request and save:
        >>> from griptape_nodes.project import Project
        >>> project = Project()
        >>> request = self._file_param.create_save_request(data=image_bytes)
        >>> result = await project.save(request)
        >>>
        >>> # With extra variables (e.g., for multiple images):
        >>> request = self._file_param.create_save_request(
        ...     data=image_bytes,
        ...     image_index=i
        ... )
        >>> result = await project.save(request)
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

        # Create parameter
        parameter = ParameterString(
            name=self._name,
            default_value=self._default_filename,
            allowed_modes=self._allowed_modes,
            tooltip=tooltip,
            input_types=["ProjectFileSaveConfig", "str"],
            output_type="str",
            traits={
                FileSystemPicker(
                    allow_files=True,
                    allow_directories=False,
                    allow_create=True,
                )
            },
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

            # Parse filename from first extra_var if available, otherwise use default
            filename = str(extra_vars.get("file_name_base", self._default_filename))
        else:
            # Use situation configuration
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
