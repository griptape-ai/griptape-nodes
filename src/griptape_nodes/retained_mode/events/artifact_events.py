"""Events for artifact operations."""

from dataclasses import dataclass
from enum import StrEnum

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
        format: Desired format for the preview (None for requesting the project default)

    Results: GeneratePreviewResultSuccess | GeneratePreviewResultFailure
    """

    macro_path: MacroPath
    format: str | None = None


@dataclass
@PayloadRegistry.register
class GeneratePreviewResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Preview generated successfully."""


@dataclass
@PayloadRegistry.register
class GeneratePreviewResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Preview generation failed."""


@dataclass
@PayloadRegistry.register
class GetPreviewForArtifactRequest(RequestPayload):
    """Get preview for an artifact.

    Args:
        macro_path: MacroPath with parsed macro and variables
        format: Desired format for the preview (None for requesting the project default)

    Results: GetPreviewForArtifactResultSuccess | GetPreviewForArtifactResultFailure
    """

    macro_path: MacroPath
    format: str | None = None


@dataclass
@PayloadRegistry.register
class GetPreviewForArtifactResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Preview retrieved successfully."""

    preview_path: MacroPath


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
