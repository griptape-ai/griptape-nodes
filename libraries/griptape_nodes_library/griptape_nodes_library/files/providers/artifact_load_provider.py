from abc import ABC, abstractmethod
from typing import Any, NamedTuple

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.files.providers.validation_result import ProviderValidationResult


class ArtifactParameterDetails(NamedTuple):
    """Details for configuring the artifact parameter."""

    # List of input types the parameter accepts (e.g., ["ImageUrlArtifact"])
    input_types: list[str]

    # Primary type for the parameter (e.g., "ImageUrlArtifact")
    type: str

    # Output type the parameter produces (e.g., "ImageUrlArtifact")
    output_type: str

    # Display name in the UI (e.g., "Image")
    display_name: str


class ArtifactLoadProvider(ABC):
    """Abstract base class for artifact load providers.

    Each provider handles loading and processing of a specific artifact type
    (image, video, audio, text) with their own additional parameters and
    validation logic.
    """

    def __init__(
        self,
        artifact: Any = None,
        internal_url: str = "",
        path: str = "",
    ) -> None:
        """Initialize provider with artifact and related information.

        Args:
            artifact: The loaded file artifact (ImageUrlArtifact, etc.)
            internal_url: Internal serving URL for the file
            path: User-friendly display path
        """
        # Current artifact being worked with
        self.artifact = artifact
        # Internal serving URL for the artifact
        self.internal_url = internal_url
        # User-friendly path for display
        self.path = path

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
        """Get provider-specific UI options for the artifact parameter.

        Returns:
            Dictionary of UI options for the artifact parameter
        """

    @abstractmethod
    def get_additional_parameters(self) -> list[Parameter]:
        """Get provider-specific parameters to add to the node.

        Returns:
            List of additional parameters this provider needs
        """

    @abstractmethod
    def validate_from_path(self, path_input: str, current_parameter_values: dict[str, Any]) -> ProviderValidationResult:
        """Validate and process a path input into a complete file loading result.

        Args:
            path_input: User-provided path string (file path or URL)
            current_parameter_values: Current values of all node parameters (for context)

        Returns:
            ProviderValidationResult with artifact, internal_url, path, and dynamic parameter updates on success,
            or error_messages on failure
        """

    @abstractmethod
    def validate_from_artifact(
        self, artifact_input: Any, current_parameter_values: dict[str, Any]
    ) -> ProviderValidationResult:
        """Validate and process an artifact input into a complete file loading result.

        Args:
            artifact_input: Artifact from another node or direct input
            current_parameter_values: Current values of all node parameters (for context)

        Returns:
            ProviderValidationResult with artifact, internal_url, path, and dynamic parameter updates on success,
            or error_messages on failure
        """
