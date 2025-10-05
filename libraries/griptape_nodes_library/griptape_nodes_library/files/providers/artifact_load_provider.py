from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode


@dataclass
class WorkspaceFileLocation:
    """Lightweight marker for a file in the workspace."""

    workspace_relative_path: Path
    absolute_path: Path


@dataclass
class ExternalFileLocation:
    """Lightweight marker for a file outside the workspace."""

    absolute_path: Path


@dataclass
class URLFileLocation:
    """Lightweight marker for a file from a URL."""

    url: str


# Type alias for all file location types
FileLocation = WorkspaceFileLocation | ExternalFileLocation | URLFileLocation


@dataclass
class ArtifactLoadProviderValidationResult:
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


class ArtifactLoadProvider(ABC):
    """Abstract base class for artifact load providers.

    Each provider handles loading and processing of a specific artifact type
    (image, video, audio, text) with access to the node context for proper
    filename generation and workspace management.
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
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create artifact from an ambiguous file location string.

        This method disambiguates the file location (URL, workspace path, or external path)
        and routes to the appropriate specialized loader method.
        """

    @abstractmethod
    def attempt_load_from_filesystem_path(
        self,
        file_location_str: str,
        file_location_type: type[FileLocation],
        current_parameter_values: dict[str, Any],
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create artifact from a filesystem path.

        Args:
            file_location_str: String representing a filesystem path
            file_location_type: The determined type (WorkspaceFileLocation or ExternalFileLocation)
            current_parameter_values: Current parameter values for dynamic updates
        """

    @abstractmethod
    def attempt_load_from_url(
        self, url_input: str, current_parameter_values: dict[str, Any], timeout: float | None = None
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create artifact from a URL.

        Args:
            url_input: URL to load from
            current_parameter_values: Current parameter values for dynamic updates
            timeout: Optional timeout in seconds for URL download
        """

    @abstractmethod
    def save_bytes_to_workspace(self, *, file_bytes: bytes, workspace_relative_path: str) -> WorkspaceFileLocation:
        """Save file bytes to workspace and return location.

        Args:
            file_bytes: Raw file bytes to save
            workspace_relative_path: Relative path within workspace (e.g., "uploads/my_file.png")

        Returns:
            WorkspaceFileLocation with saved file details
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
    def is_location_external_to_workspace(self, location: FileLocation) -> bool:
        """Returns True if location is outside workspace and can be copied.

        Args:
            location: File location instance

        Returns:
            True if location is external (can be copied to workspace), False otherwise
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
    def copy_location_to_workspace(
        self,
        location: FileLocation,
        artifact: Any,
        parameter_name: str,
    ) -> WorkspaceFileLocation:
        """Copy file from location to workspace.

        Args:
            location: The file location to copy
            artifact: The current artifact (for extracting bytes if needed)
            parameter_name: Parameter name for filename generation

        Returns:
            WorkspaceFileLocation with the saved file details

        Raises:
            TypeError: If the location type is not supported for copying
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
    def generate_upload_filename(
        workflow_name: str,
        node_name: str,
        parameter_name: str,
        original_filename: str,
    ) -> str:
        """Generate a collision-free filename for uploaded files.

        Args:
            workflow_name: Name of the current workflow
            node_name: Name of the node
            parameter_name: Name of the parameter
            original_filename: Original filename

        Returns:
            Generated collision-free filename
        """
        import re

        # Sanitize components for filename safety
        def sanitize(name: str) -> str:
            """Replace unsafe characters with underscores."""
            return re.sub(r'[<>:"/\\|?*]', "_", name)

        safe_workflow = sanitize(workflow_name)
        safe_node = sanitize(node_name)
        safe_param = sanitize(parameter_name)
        safe_filename = sanitize(original_filename)

        return f"{safe_workflow}_{safe_node}_{safe_param}_{safe_filename}"

    @staticmethod
    def determine_file_location(file_location_str: str) -> FileLocation:
        """Factory that creates a FileLocation instance from a string.

        Args:
            file_location_str: String representing a file location (URL or filesystem path)

        Returns:
            FileLocation instance (WorkspaceFileLocation, ExternalFileLocation, or URLFileLocation)
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Check if URL
        if ArtifactLoadProvider.is_url(file_location_str):
            return URLFileLocation(url=file_location_str)

        # Otherwise it's a filesystem path
        file_path = Path(file_location_str)
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        if not file_path.is_absolute():
            file_path = workspace_path / file_path

        resolved_file_path = file_path.resolve()

        try:
            relative_path = resolved_file_path.relative_to(workspace_path)
            return WorkspaceFileLocation(workspace_relative_path=relative_path, absolute_path=resolved_file_path)
        except ValueError:
            return ExternalFileLocation(absolute_path=resolved_file_path)
