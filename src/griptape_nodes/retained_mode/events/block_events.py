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
class ListBlocksRequest(RequestPayload):
    """List block identifiers within a timeline."""

    timeline_name: str


@dataclass
@PayloadRegistry.register
class ListBlocksResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Blocks listed successfully."""

    timeline_name: str
    block_ids: list[str]


@dataclass
@PayloadRegistry.register
class ListBlocksResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Block listing failed."""


@dataclass
@PayloadRegistry.register
class GetBlockRequest(RequestPayload):
    """Get a specific block's content from a timeline."""

    timeline_name: str
    block_id: str


@dataclass
@PayloadRegistry.register
class GetBlockResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Block content retrieved successfully."""

    timeline_name: str
    block_id: str
    content: Any


@dataclass
@PayloadRegistry.register
class GetBlockResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Block retrieval failed."""


@dataclass
@PayloadRegistry.register
class WriteBlockRequest(RequestPayload):
    """Create or replace a block within a timeline by id."""

    timeline_name: str
    block_id: str
    content: Any


@dataclass
@PayloadRegistry.register
class WriteBlockResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Block written and saved successfully."""

    timeline_name: str
    block_id: str


@dataclass
@PayloadRegistry.register
class WriteBlockResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Block write failed."""

@dataclass
@PayloadRegistry.register
class CreateBlockRequest(RequestPayload):
    """Create a new block within a timeline; fails if it already exists."""

    timeline_name: str
    block_id: str
    content: Any


@dataclass
@PayloadRegistry.register
class CreateBlockResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Block created successfully."""

    timeline_name: str
    block_id: str


@dataclass
@PayloadRegistry.register
class CreateBlockResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Block create failed."""


@dataclass
@PayloadRegistry.register
class DeleteBlockRequest(RequestPayload):
    """Delete a block from a timeline."""

    timeline_name: str
    block_id: str


@dataclass
@PayloadRegistry.register
class DeleteBlockResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Block deleted successfully."""

    timeline_name: str
    block_id: str


@dataclass
@PayloadRegistry.register
class DeleteBlockResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Block delete failed."""


