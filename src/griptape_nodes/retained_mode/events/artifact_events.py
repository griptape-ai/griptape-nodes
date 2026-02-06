"""Events for artifact operations."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.events.project_events import MacroPath


class ArtifactFailureReason(StrEnum):
    """Classification of artifact operation failure reasons."""

    # File errors
    FILE_NOT_FOUND = "file_not_found"  # Source artifact doesn't exist
    PERMISSION_DENIED = "permission_denied"  # No read/write permission

    # Format errors
    UNSUPPORTED_FORMAT = "unsupported_format"  # Can't generate preview for this file type

    # Macro errors
    MACRO_RESOLUTION_FAILED = "macro_resolution_failed"  # Failed to resolve MacroPath
    MISSING_VARIABLES = "missing_variables"  # Missing required macro variables

    # Situation errors
    SITUATION_NOT_FOUND = "situation_not_found"  # No save_preview situation defined

    # Generation errors
    PREVIEW_GENERATION_FAILED = "preview_generation_failed"  # Failed to generate preview

    # Generic errors
    IO_ERROR = "io_error"  # Generic I/O error
    UNKNOWN = "unknown"  # Unexpected error


@dataclass
@PayloadRegistry.register
class GeneratePreviewRequest(RequestPayload):
    """Generate a preview for an artifact.

    Args:
        macro_path: MacroPath with parsed macro and variables
        artifact_provider_name: Specific provider to use
        format: Desired format for the preview (None for requesting the project default)
        preview_generator_name: Preview generator to use (None for provider default)
        preview_generator_parameters: Parameters for the preview generator (e.g., max_width, max_height)
        generate_preview_metadata_json: Whether to generate metadata JSON file alongside preview

    Results: GeneratePreviewResultSuccess | GeneratePreviewResultFailure
    """

    macro_path: MacroPath
    artifact_provider_name: str
    format: str | None = None
    preview_generator_name: str | None = None
    preview_generator_parameters: dict[str, Any] = field(default_factory=dict)
    generate_preview_metadata_json: bool = False


@dataclass
@PayloadRegistry.register
class GeneratePreviewResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Preview generated successfully.

    Attributes:
        paths_to_preview: Absolute path(s) to generated preview file(s).
            - str: Single preview file path (e.g., "/path/to/image.png.webp")
            - dict[str, str]: Multiple preview files with semantic keys
              (e.g., {"mask_r": "/path/to/output_R.png", "mask_g": "/path/to/output_G.png"})
    """

    paths_to_preview: str | dict[str, str]


@dataclass
@PayloadRegistry.register
class GeneratePreviewResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Preview generation failed."""


@dataclass
@PayloadRegistry.register
class GeneratePreviewFromDefaultsRequest(RequestPayload):
    """Generate a preview for an artifact using ALL defaults from config.

    This is a high-level convenience request that reads all settings from config
    (default preview format, default preview generator, and generator parameters),
    then delegates to GeneratePreviewRequest with all parameters filled in.

    No overrides allowed - uses config defaults exclusively.

    Args:
        macro_path: MacroPath with parsed macro and variables
        artifact_provider_name: Specific provider to use

    Results: GeneratePreviewFromDefaultsResultSuccess | GeneratePreviewFromDefaultsResultFailure
    """

    macro_path: MacroPath
    artifact_provider_name: str


@dataclass
@PayloadRegistry.register
class GeneratePreviewFromDefaultsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Preview generated successfully using config defaults.

    Attributes:
        paths_to_preview: Absolute path(s) to generated preview file(s).
            - str: Single preview file path (e.g., "/path/to/image.png.webp")
            - dict[str, str]: Multiple preview files with semantic keys
              (e.g., {"mask_r": "/path/to/output_R.png", "mask_g": "/path/to/output_G.png"})
    """

    paths_to_preview: str | dict[str, str]


@dataclass
@PayloadRegistry.register
class GeneratePreviewFromDefaultsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to generate preview using config defaults."""


@dataclass
@PayloadRegistry.register
class GetPreviewForArtifactRequest(RequestPayload):
    """Get preview for an artifact.

    Args:
        macro_path: MacroPath with parsed macro and variables
        generate_preview_if_necessary: Whether to auto-generate if preview missing/stale (future feature)

    Results: GetPreviewForArtifactResultSuccess | GetPreviewForArtifactResultFailure
    """

    macro_path: MacroPath
    generate_preview_if_necessary: bool = True


@dataclass
@PayloadRegistry.register
class GetPreviewForArtifactResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Preview retrieved successfully.

    Attributes:
        paths_to_preview: Absolute path(s) to retrieved preview file(s).
            - str: Single preview file path (e.g., "/path/to/image.png.webp")
            - dict[str, str]: Multiple preview files with semantic keys
              (e.g., {"mask_r": "/path/to/output_R.png", "mask_g": "/path/to/output_G.png"})
    """

    paths_to_preview: str | dict[str, str]


@dataclass
@PayloadRegistry.register
class GetPreviewForArtifactResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to get preview for artifact."""


@dataclass
@PayloadRegistry.register
class RegisterArtifactProviderRequest(RequestPayload):
    """Register an artifact provider.

    Args:
        provider_class: The provider class to instantiate and register

    Results: RegisterArtifactProviderResultSuccess | RegisterArtifactProviderResultFailure
    """

    provider_class: type


@dataclass
@PayloadRegistry.register
class RegisterArtifactProviderResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Artifact provider registered successfully."""


@dataclass
@PayloadRegistry.register
class RegisterArtifactProviderResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to register artifact provider."""


@dataclass
@PayloadRegistry.register
class ListArtifactProvidersRequest(RequestPayload):
    """List all registered artifact providers.

    Results: ListArtifactProvidersResultSuccess | ListArtifactProvidersResultFailure
    """


@dataclass
@PayloadRegistry.register
class ListArtifactProvidersResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successfully listed artifact providers."""

    friendly_names: list[str]


@dataclass
@PayloadRegistry.register
class ListArtifactProvidersResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to list artifact providers."""


@dataclass
@PayloadRegistry.register
class GetArtifactProviderDetailsRequest(RequestPayload):
    """Get details for a specific artifact provider by friendly name.

    Args:
        friendly_name: The friendly name of the provider (case-insensitive)

    Results: GetArtifactProviderDetailsResultSuccess | GetArtifactProviderDetailsResultFailure
    """

    friendly_name: str


@dataclass
@PayloadRegistry.register
class GetArtifactProviderDetailsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successfully retrieved provider details."""

    friendly_name: str
    supported_formats: set[str]
    preview_formats: set[str]
    registered_preview_generators: list[str]


@dataclass
@PayloadRegistry.register
class GetArtifactProviderDetailsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to get provider details."""


@dataclass
@PayloadRegistry.register
class RegisterPreviewGeneratorRequest(RequestPayload):
    """Register a preview generator with a provider.

    Args:
        provider_friendly_name: The friendly name of the provider
        preview_generator_class: The preview generator class to register

    Results: RegisterPreviewGeneratorResultSuccess | RegisterPreviewGeneratorResultFailure
    """

    provider_friendly_name: str
    preview_generator_class: type


@dataclass
@PayloadRegistry.register
class RegisterPreviewGeneratorResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Preview generator registered successfully."""


@dataclass
@PayloadRegistry.register
class RegisterPreviewGeneratorResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to register preview generator."""


@dataclass
@PayloadRegistry.register
class ListPreviewGeneratorsRequest(RequestPayload):
    """List all registered preview generators for a provider.

    Args:
        provider_friendly_name: The friendly name of the provider

    Results: ListPreviewGeneratorsResultSuccess | ListPreviewGeneratorsResultFailure
    """

    provider_friendly_name: str


@dataclass
@PayloadRegistry.register
class ListPreviewGeneratorsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successfully listed preview generators."""

    preview_generator_names: list[str]


@dataclass
@PayloadRegistry.register
class ListPreviewGeneratorsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to list preview generators."""


@dataclass
@PayloadRegistry.register
class GetPreviewGeneratorDetailsRequest(RequestPayload):
    """Get details for a specific preview generator by friendly name.

    Args:
        provider_friendly_name: The friendly name of the provider
        preview_generator_friendly_name: The friendly name of the preview generator (case-insensitive)

    Results: GetPreviewGeneratorDetailsResultSuccess | GetPreviewGeneratorDetailsResultFailure
    """

    provider_friendly_name: str
    preview_generator_friendly_name: str


@dataclass
@PayloadRegistry.register
class GetPreviewGeneratorDetailsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successfully retrieved preview generator details."""

    friendly_name: str
    supported_source_formats: set[str]
    supported_preview_formats: set[str]
    parameters: dict[str, tuple[object, bool]]


@dataclass
@PayloadRegistry.register
class GetPreviewGeneratorDetailsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to get preview generator details."""
