from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, NamedTuple

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode


@dataclass
class ArtifactLoadProviderValidationResult:
    """Result of provider validation containing all updates or error information.

    Always contains all fields - LoadFile uses was_successful to determine
    whether to apply the updates or show the result details.
    """

    # The validated file artifact (ImageUrlArtifact, etc.) ready for use
    artifact: Any

    # Internal serving URL for the file (http://localhost:8124/static-uploads/...)
    internal_url: str

    # User-friendly display path shown in the path parameter
    path: str

    # Updates for provider-specific parameters (e.g., mask extraction results)
    dynamic_parameter_updates: dict[str, Any]

    # Whether the operation was successful
    was_successful: bool

    # Details about the operation (error message or success info)
    result_details: str

    def __init__(  # noqa: PLR0913
        self,
        *,
        was_successful: bool,
        result_details: str,
        artifact: Any = None,
        internal_url: str = "",
        path: str = "",
        dynamic_parameter_updates: dict[str, Any] | None = None,
    ) -> None:
        """Initialize validation result with all fields."""
        self.was_successful = was_successful
        self.artifact = artifact
        self.internal_url = internal_url
        self.path = path
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

    # Display name in the UI (e.g., "Image")
    display_name: str


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
    def can_handle_path(self, path_input: str) -> bool:
        """Lightweight check if this provider can handle the given file path."""

    @abstractmethod
    def can_handle_url(self, url_input: str) -> bool:
        """Lightweight check if this provider can handle the given URL."""

    @abstractmethod
    def can_handle_artifact(self, artifact_input: Any) -> bool:
        """Lightweight check if this provider can handle the given artifact."""

    @abstractmethod
    def attempt_load_from_path(
        self, path_input: str, current_parameter_values: dict[str, Any]
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create artifact from a file path."""

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
