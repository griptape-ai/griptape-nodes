"""Manager for artifact operations."""

from griptape_nodes.retained_mode.events.artifact_events import (
    GeneratePreviewRequest,
    GeneratePreviewResultFailure,
    GeneratePreviewResultSuccess,
    GetPreviewForArtifactRequest,
    GetPreviewForArtifactResultFailure,
    GetPreviewForArtifactResultSuccess,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager


class ArtifactManager:
    """Manages artifact operations including preview generation."""

    def __init__(self, event_manager: EventManager | None = None) -> None:
        """Initialize the ArtifactManager."""
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                GeneratePreviewRequest, self.on_handle_generate_preview_request
            )
            event_manager.assign_manager_to_request_type(
                GetPreviewForArtifactRequest, self.on_handle_get_preview_for_artifact_request
            )

    def on_handle_generate_preview_request(
        self, request: GeneratePreviewRequest
    ) -> GeneratePreviewResultSuccess | GeneratePreviewResultFailure:
        """Handle generate preview request."""
        return GeneratePreviewResultFailure(result_details="Not implemented yet")

    def on_handle_get_preview_for_artifact_request(
        self, request: GetPreviewForArtifactRequest
    ) -> GetPreviewForArtifactResultSuccess | GetPreviewForArtifactResultFailure:
        """Handle get preview for artifact request."""
        return GetPreviewForArtifactResultFailure(result_details="Not implemented yet")
