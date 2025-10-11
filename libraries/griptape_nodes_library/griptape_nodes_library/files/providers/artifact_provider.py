import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry

logger = logging.getLogger("griptape_nodes")


@dataclass
class FileLocation:
    """Base class for all file location types."""

    def get_filename(self) -> str:
        """Get the filename from this location."""
        raise NotImplementedError


@dataclass
class OnDiskFileLocation(FileLocation):
    """Base class for files that exist on disk."""

    absolute_path: Path

    def get_filename(self) -> str:
        """Get the filename from the absolute path."""
        return self.absolute_path.name


@dataclass
class ProjectFileLocation(OnDiskFileLocation):
    """File in the project."""

    project_relative_path: Path


@dataclass
class ExternalFileLocation(OnDiskFileLocation):
    """File outside the project."""


@dataclass
class URLFileLocation(FileLocation):
    """File from a URL."""

    url: str

    def get_filename(self) -> str:
        """Get the filename from the URL, or raise if not determinable."""
        url_path = Path(self.url)
        filename = url_path.name
        if not filename or not Path(filename).suffix:
            msg = f"Cannot determine filename with extension from URL: {self.url}"
            raise ValueError(msg)
        return filename


@dataclass
class ArtifactProviderValidationResult:
    """Result of provider validation containing all updates or error information.

    Always contains all fields - LoadFile uses was_successful to determine
    whether to apply the updates or show the result details.
    """

    # The validated file artifact (ImageUrlArtifact, etc.) ready for use
    artifact: Any

    # FileLocation transport object (None for errors or non-file sources)
    location: FileLocation | None

    # Updates for provider-specific parameters (e.g., mask extraction results)
    dynamic_parameter_updates: dict[str, Any]

    # Whether the operation was successful
    was_successful: bool

    # Details about the operation (error message or success info)
    result_details: str

    def __init__(
        self,
        *,
        was_successful: bool,
        result_details: str,
        artifact: Any = None,
        location: FileLocation | None = None,
        dynamic_parameter_updates: dict[str, Any] | None = None,
    ) -> None:
        """Initialize validation result with all fields."""
        self.was_successful = was_successful
        self.artifact = artifact
        self.location = location
        self.dynamic_parameter_updates = dynamic_parameter_updates or {}
        self.result_details = result_details


class ArtifactParameterDetails(NamedTuple):
    """Details for configuring the artifact parameter."""

    # List of input types the parameter accepts (e.g., ["ImageUrlArtifact"])
    input_types: list[str]

    # Primary type for the parameter (e.g., "ImageUrlArtifact")
    type: str

    # Output type the parameter produces (e.g., "ImageUrlArtifact")
    output_type: str


class ArtifactProvider(ABC):
    """Abstract base class for artifact load providers.

    Each provider handles loading and processing of a specific artifact type
    (image, video, audio, text) with access to the node context for proper
    filename generation and project management.
    """

    def __init__(self, node: BaseNode, *, path_parameter: Parameter) -> None:
        """Initialize provider with node reference and required parameters.

        Args:
            node: The node that owns this provider
            path_parameter: The parameter that holds the file path input
        """
        self.node = node
        self.path_parameter = path_parameter

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of this provider (e.g., 'Image', 'Video')."""

    @property
    @abstractmethod
    def artifact_type(self) -> str:
        """The artifact type this provider produces (e.g., 'ImageUrlArtifact')."""

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """Set of file extensions this provider supports (e.g., {'.png', '.jpg'})."""

    @property
    @abstractmethod
    def url_content_type_prefix(self) -> str:
        """Content-type prefix for URL validation (e.g., 'image/', 'video/')."""

    @property
    @abstractmethod
    def default_extension(self) -> str:
        """Default extension to use when generating filenames (e.g., 'png')."""

    @abstractmethod
    def get_artifact_parameter_details(self) -> ArtifactParameterDetails:
        """Get complete artifact parameter configuration details."""

    @abstractmethod
    def get_artifact_ui_options(self) -> dict[str, Any]:
        """Get provider-specific UI options for the artifact parameter."""

    @abstractmethod
    def get_additional_parameters(self) -> list[Parameter]:
        """Get provider-specific parameters to add to the node."""

    @abstractmethod
    def can_handle_file_location(self, file_location_input: str) -> bool:
        """Lightweight check if this provider can handle the given file location input."""

    @abstractmethod
    def attempt_load_from_file_location(
        self, file_location_str: str, current_parameter_values: dict[str, Any]
    ) -> ArtifactProviderValidationResult:
        """Attempt to load and create artifact from an ambiguous file location string.

        This method disambiguates the file location (URL, project path, or external path)
        and routes to the appropriate specialized loader method.
        """

    @abstractmethod
    def attempt_load_from_filesystem_path(
        self,
        location: OnDiskFileLocation,
        current_parameter_values: dict[str, Any],
    ) -> ArtifactProviderValidationResult:
        """Attempt to load and create artifact from a filesystem path.

        Args:
            location: The OnDiskFileLocation (ProjectFileLocation or ExternalFileLocation)
            current_parameter_values: Current parameter values for dynamic updates
        """

    @abstractmethod
    def attempt_load_from_url(
        self, location: URLFileLocation, current_parameter_values: dict[str, Any], timeout: float | None = None
    ) -> ArtifactProviderValidationResult:
        """Attempt to load and create artifact from a URL.

        Args:
            location: URLFileLocation with the URL to load from
            current_parameter_values: Current parameter values for dynamic updates
            timeout: Optional timeout in seconds for URL download
        """

    @abstractmethod
    def save_bytes_to_disk(self, *, file_bytes: bytes, location: OnDiskFileLocation) -> OnDiskFileLocation:
        """Save file bytes to disk at the specified location.

        Args:
            file_bytes: Raw file bytes to save
            location: OnDiskFileLocation specifying where to save (can be ProjectFileLocation or ExternalFileLocation)

        Returns:
            The location that was passed in (for chaining/confirmation)
        """

    @abstractmethod
    def get_externally_accessible_url(self, location: FileLocation) -> str:
        """Convert file location to URL the frontend can fetch.

        Args:
            location: File location instance

        Returns:
            URL string that frontend can use to fetch the file
        """

    @abstractmethod
    def get_display_path(self, location: FileLocation) -> str:
        """Get user-facing path string for UI display.

        Args:
            location: File location instance

        Returns:
            Display path string for UI
        """

    @abstractmethod
    def get_source_path(self, location: FileLocation) -> str:
        """Get the original source path/URL provided by user.

        Args:
            location: File location instance

        Returns:
            Original source path or URL string
        """

    @abstractmethod
    def is_location_external_to_project(self, location: FileLocation) -> bool:
        """Returns True if location is outside project and can be copied.

        Args:
            location: File location instance

        Returns:
            True if location is external (can be copied to project), False otherwise
        """

    @abstractmethod
    def get_location_display_detail(self, location: FileLocation) -> str:
        """Get the URL or path detail to show user.

        Args:
            location: File location instance

        Returns:
            String detail to display (URL, path, etc.)
        """

    @abstractmethod
    def copy_file_location_to_disk(
        self,
        source_location: FileLocation,
        destination_location: OnDiskFileLocation,
        artifact: Any,
    ) -> OnDiskFileLocation:
        """Copy file from source location to destination location on disk.

        Args:
            source_location: The source file location to copy from (any FileLocation type)
            destination_location: Where to save the file (ProjectFileLocation or ExternalFileLocation)
            artifact: The current artifact (for extracting download info from URLs)

        Returns:
            The destination_location passed in (for confirmation)

        Raises:
            TypeError: If the source location type is not supported for copying
        """

    def _finalize_result_with_dynamic_updates(
        self,
        *,
        artifact: Any,  # noqa: ARG002
        current_values: dict[str, Any],  # noqa: ARG002
    ) -> dict[str, Any]:
        """Process provider-specific dynamic parameter updates (e.g., mask extraction).

        Default implementation returns empty dict. Providers should override to add
        their own dynamic parameter processing logic.
        """
        return {}

    @staticmethod
    def is_url(path_str: str) -> bool:
        """Check if the path string is a URL.

        Args:
            path_str: Path string to check

        Returns:
            True if the string is a URL
        """
        return path_str.startswith(("http://", "https://"))

    @staticmethod
    def normalize_path_input(path_input: Any) -> str:
        """Normalize various path inputs to a string.

        Args:
            path_input: Path input (string, Path, or other)

        Returns:
            Normalized string representation
        """
        if path_input is None:
            return ""

        if isinstance(path_input, Path):
            return str(path_input)

        # Convert to string and strip surrounding quotes
        path_str = str(path_input).strip()

        # Strip surrounding quotes only if they match (from 'Copy as Pathname')
        if len(path_str) >= 2 and (  # noqa: PLR2004
            (path_str.startswith("'") and path_str.endswith("'"))
            or (path_str.startswith('"') and path_str.endswith('"'))
        ):
            return path_str[1:-1]
        return path_str

    @staticmethod
    def get_workflow_directory() -> Path:
        """Get the workflow's directory, or workspace if workflow cannot be determined.

        Returns directory where workflow files should be stored. For saved workflows,
        uses the workflow's actual directory. For unsaved workflows, falls back to
        workspace root with a warning.

        Returns:
            Path relative to workspace (e.g., Path("myworkflow")), or absolute path if outside project

        Raises:
            RuntimeError: If workflow context cannot be determined
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        workflow_name = GriptapeNodes.ContextManager().get_current_workflow_name()
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        try:
            workflow = WorkflowRegistry.get_workflow_by_name(workflow_name)
            workflow_file_path = Path(WorkflowRegistry.get_complete_file_path(workflow.file_path))
            workflow_directory = workflow_file_path.parent
        except KeyError:
            # Workflow not in registry (unsaved) - use workspace root
            logger.warning(
                "Workflow '%s' not saved yet, using workspace directory. Files will be stored at workspace root.",
                workflow_name,
            )
            workflow_directory = workspace_path

        try:
            final_dir = workflow_directory.relative_to(workspace_path)
        except ValueError:
            logger.warning("Workflow directory is outside project: %s", workflow_directory)
            final_dir = workflow_directory

        return final_dir

    @staticmethod
    def generate_workflow_file_location(*, subdirectory: str, filename: str) -> OnDiskFileLocation:
        """Generate file location in workflow subdirectory.

        Places files in {workflow_dir}/{workflow_name}/{subdirectory}/{filename}.
        This keeps all workflow files packaged together under a workflow-specific directory.

        Args:
            subdirectory: Subdirectory within workflow directory (e.g., "inputs", "outputs", "thumbnails")
            filename: Filename to use (e.g., "cdn_example_com_image.jpg")

        Returns:
            ProjectFileLocation if workflow is inside project, ExternalFileLocation if outside

        Example:
            location = ArtifactProvider.generate_workflow_file_location(
                subdirectory="inputs",
                filename="cdn_example_com_image.png"
            )
            # Result: workspace/myworkflow/myworkflow/inputs/cdn_example_com_image.png
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        workflow_name = GriptapeNodes.ContextManager().get_current_workflow_name()
        workflow_directory = ArtifactProvider.get_workflow_directory()
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        if workflow_directory.is_absolute():
            # Workflow is outside project - return ExternalFileLocation
            absolute_path = workflow_directory / workflow_name / subdirectory / filename
            return ExternalFileLocation(absolute_path=absolute_path)

        # Workflow is inside project - return ProjectFileLocation
        project_relative_path = workflow_directory / workflow_name / subdirectory / filename
        absolute_path = workspace_path / project_relative_path

        return ProjectFileLocation(
            project_relative_path=project_relative_path,
            absolute_path=absolute_path,
        )

    @staticmethod
    def determine_file_location(file_location_str: str) -> FileLocation:
        """Factory that creates a FileLocation instance from a string.

        Args:
            file_location_str: String representing a file location (URL or filesystem path)

        Returns:
            FileLocation instance (ProjectFileLocation, ExternalFileLocation, or URLFileLocation)
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Check if URL
        if ArtifactProvider.is_url(file_location_str):
            return URLFileLocation(url=file_location_str)

        # Otherwise it's a filesystem path
        file_path = Path(file_location_str)
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        if not file_path.is_absolute():
            file_path = workspace_path / file_path

        resolved_file_path = file_path.resolve()

        try:
            relative_path = resolved_file_path.relative_to(workspace_path)
            return ProjectFileLocation(project_relative_path=relative_path, absolute_path=resolved_file_path)
        except ValueError:
            return ExternalFileLocation(absolute_path=resolved_file_path)
