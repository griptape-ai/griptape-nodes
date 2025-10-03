from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode


class FileLocation(ABC):
    """Base class for file location transport - carries location type and paths.

    This is a pure data transport mechanism with no business logic.
    Business logic (UI decisions, copy buttons, etc.) belongs in nodes/providers.
    """

    @abstractmethod
    def get_externally_accessible_url(self) -> str:
        """Return URL that can be used to access this file from the frontend."""

    @abstractmethod
    def get_display_path(self) -> str:
        """Return user-facing path string shown in UI."""

    @abstractmethod
    def get_source_path(self) -> str:
        """Return the original source path/URL provided by user."""

    @abstractmethod
    def get_filesystem_path(self) -> Path:
        """Return Path for filesystem locations.

        Raises:
            TypeError: If this is not a filesystem location (e.g., URL)
        """

    @abstractmethod
    def get_url_string(self) -> str:
        """Return URL string for URL locations.

        Raises:
            TypeError: If this is not a URL location (e.g., filesystem path)
        """


class OnDiskFileLocation(FileLocation):
    """Base class for files on local filesystem (workspace or external)."""

    def __init__(self, externally_accessible_url: str, absolute_path: Path):
        self.externally_accessible_url = externally_accessible_url
        self.absolute_path = absolute_path

    def get_externally_accessible_url(self) -> str:
        return self.externally_accessible_url

    def get_filesystem_path(self) -> Path:
        return self.absolute_path

    def get_url_string(self) -> str:
        msg = f"{self.__class__.__name__} is not a URL"
        raise TypeError(msg)


class WorkspaceFileLocation(OnDiskFileLocation):
    """File located inside the workspace directory."""

    def __init__(self, externally_accessible_url: str, workspace_relative_path: Path, absolute_path: Path):
        super().__init__(externally_accessible_url, absolute_path)
        self.workspace_relative_path = workspace_relative_path

    def get_display_path(self) -> str:
        return str(self.workspace_relative_path)

    def get_source_path(self) -> str:
        return str(self.workspace_relative_path)


class ExternalFileLocation(OnDiskFileLocation):
    """File located outside workspace on local filesystem."""

    def get_display_path(self) -> str:
        return str(self.absolute_path)

    def get_source_path(self) -> str:
        return str(self.absolute_path)


class URLFileLocation(FileLocation):
    """File accessed via HTTP(S) URL."""

    def __init__(self, url: str):
        self.url = url

    def get_externally_accessible_url(self) -> str:
        return self.url

    def get_display_path(self) -> str:
        return self.url

    def get_source_path(self) -> str:
        return self.url

    def get_filesystem_path(self) -> Path:
        msg = "URLFileLocation is not a filesystem path"
        raise TypeError(msg)

    def get_url_string(self) -> str:
        return self.url


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
    def can_handle_artifact(self, artifact_input: Any) -> bool:
        """Lightweight check if this provider can handle the given artifact."""

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
        self, url_input: str, current_parameter_values: dict[str, Any]
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create artifact from a URL."""

    @abstractmethod
    def attempt_load_from_artifact(
        self, artifact_input: Any, current_parameter_values: dict[str, Any]
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and normalize an artifact input."""

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
    def determine_file_location_type(file_location_str: str) -> type[FileLocation]:
        """Determine file location type from string (URL, workspace path, or external path).

        Args:
            file_location_str: String representing a file location (URL or filesystem path)

        Returns:
            FileLocation type (URLFileLocation, WorkspaceFileLocation, or ExternalFileLocation)
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Check if URL
        if ArtifactLoadProvider.is_url(file_location_str):
            return URLFileLocation

        # Otherwise it's a filesystem path
        file_path = Path(file_location_str)
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        if not file_path.is_absolute():
            file_path = workspace_path / file_path

        resolved_file_path = file_path.resolve()

        try:
            resolved_file_path.relative_to(workspace_path)
        except ValueError:
            return ExternalFileLocation
        else:
            return WorkspaceFileLocation
