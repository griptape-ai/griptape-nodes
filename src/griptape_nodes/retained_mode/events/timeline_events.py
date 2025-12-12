from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class ListTimelinesRequest(RequestPayload):
    """List all timelines available in the workspace timelines directory."""


@dataclass
@PayloadRegistry.register
class ListTimelinesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Timelines listed successfully."""

    names: list[str]


@dataclass
@PayloadRegistry.register
class ListTimelinesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Timeline listing failed."""


@dataclass
@PayloadRegistry.register
class GetTimelineRequest(RequestPayload):
    """Get a specific timeline by name."""

    name: str


@dataclass
@PayloadRegistry.register
class GetTimelineResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Timeline content retrieved successfully."""

    name: str
    content: Any


@dataclass
@PayloadRegistry.register
class GetTimelineResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Timeline retrieval failed."""


@dataclass
@PayloadRegistry.register
class WriteTimelineRequest(RequestPayload):
    """Create or replace a timeline by name with provided content.

    Content is persisted as JSON if dict/list, otherwise as UTF-8 text.
    """

    name: str
    content: Any


@dataclass
@PayloadRegistry.register
class WriteTimelineResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Timeline written and saved successfully."""

    name: str
    path: str


@dataclass
@PayloadRegistry.register
class WriteTimelineResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Timeline write failed."""

@dataclass
@PayloadRegistry.register
class CreateTimelineRequest(RequestPayload):
    """Create a new timeline by name; fails if it already exists."""

    name: str
    content: Any | None = None  # Optional initial content; defaults to {"blocks": {}}


@dataclass
@PayloadRegistry.register
class CreateTimelineResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Timeline created successfully."""

    name: str
    path: str


@dataclass
@PayloadRegistry.register
class CreateTimelineResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Timeline create failed."""


@dataclass
@PayloadRegistry.register
class DeleteTimelineRequest(RequestPayload):
    """Delete an existing timeline by name."""

    name: str


@dataclass
@PayloadRegistry.register
class DeleteTimelineResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Timeline deleted successfully."""

    name: str
    path: str


@dataclass
@PayloadRegistry.register
class DeleteTimelineResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Timeline delete failed."""


