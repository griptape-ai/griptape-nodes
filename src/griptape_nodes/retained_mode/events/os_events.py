from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileRequest(RequestPayload):
    """Open a file using the operating system's associated application.

    Use when: Opening generated files, launching external applications,
    providing file viewing capabilities, implementing file associations.

    Results: OpenAssociatedFileResultSuccess | OpenAssociatedFileResultFailure (file not found, no association)
    """

    path_to_file: str


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File opened successfully with associated application."""


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File opening failed. Common causes: file not found, no associated application, permission denied."""
