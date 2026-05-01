"""Events for querying permission state.

Two request types:

- `EvaluatePermissionRequest` asks whether a permission is granted *for a specific
  node type in a specific library*. The manager returns one of three result types:
    * `EvaluatePermissionGranted` - the permission is granted.
    * `EvaluatePermissionDenied` - the permission was evaluated and denied;
      `denial_reasons` enumerates every reason that applied.
    * `EvaluatePermissionResultFailure` - evaluation could not complete (unknown
      library or node type). The caller supplied a subject the engine cannot
      resolve; this is distinct from a policy denial.
- `ListModelEntitlementsRequest` asks for the subset of a node type's declared
  model entitlements that are permitted. Convenience over per-entitlement
  `EvaluatePermissionRequest` calls for the common "render a permitted-options
  dropdown" case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from griptape_nodes.node_library.workflow_registry import LibraryNameAndNodeType
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_properties import ModelEntitlement


class DenialReasonCode(StrEnum):
    """Why a permission evaluation returned a denial.

    A single denial can carry multiple reasons; the manager accumulates every reason
    that applies so callers can surface all of them. Codes apply only to denial
    results - evaluation failures (unknown library, unknown node type) surface as
    `EvaluatePermissionResultFailure` with their own `failure_code`.
    """

    UNKNOWN_PERMISSION = "UNKNOWN_PERMISSION"
    DECLARATION_SCOPE_VIOLATION = "DECLARATION_SCOPE_VIOLATION"
    POLICY_DENIED = "POLICY_DENIED"


class EvaluationFailureCode(StrEnum):
    """Why a permission evaluation could not complete.

    Failures differ from denials: they mean the caller supplied a subject the engine
    cannot resolve (e.g., the library isn't registered), not that the answer was 'no'.
    """

    UNKNOWN_LIBRARY = "UNKNOWN_LIBRARY"
    UNKNOWN_NODE_TYPE = "UNKNOWN_NODE_TYPE"


@dataclass
class DenialReason:
    """A single reason that contributed to a permission denial."""

    code: DenialReasonCode
    message: str


@dataclass
@PayloadRegistry.register
class EvaluatePermissionRequest(RequestPayload):
    """Ask whether the named permission is granted for a specific node type.

    Args:
        subject: Library name + node_type identifying the node whose declared
            permission surface the manager consults.
        permission_name: Permission name the caller is asking about.
    """

    subject: LibraryNameAndNodeType
    permission_name: str


@dataclass
@PayloadRegistry.register
class EvaluatePermissionGranted(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Permission was granted."""


@dataclass
@PayloadRegistry.register
class EvaluatePermissionDenied(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Permission was denied.

    Args:
        denial_reasons: Every reason the manager found to deny the request. The list
            is never empty (an empty denial-reason list would be a grant, not a
            denial). Callers can render all reasons.
    """

    denial_reasons: list[DenialReason] = field(default_factory=list)


@dataclass
@PayloadRegistry.register
class EvaluatePermissionResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Evaluation could not complete.

    Args:
        failure_code: Machine-readable reason the subject could not be resolved.
    """

    failure_code: EvaluationFailureCode | None = None


@dataclass
@PayloadRegistry.register
class ListModelEntitlementsRequest(RequestPayload):
    """Ask for the subset of a node type's declared model entitlements that are permitted.

    The manager walks the node's `ModelUsageNodeProperty` entries, resolves each to a
    `ModelEntitlement` on the library's `ModelCatalogLibraryProperty`, and returns the
    entitlements whose `requires_permission` is granted (or None). Order matches the
    node's author-declared property order.

    Args:
        subject: Library name + node_type identifying the node whose declared model
            entitlements the manager evaluates.
    """

    subject: LibraryNameAndNodeType


@dataclass
@PayloadRegistry.register
class ListModelEntitlementsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Model-entitlement listing completed.

    Args:
        entitlements: The entitlements the caller is permitted to use, in author-
            declared order. Empty when the node declares no `ModelUsageNodeProperty`
            entries, when the library has no `ModelCatalogLibraryProperty`, or when
            every entitlement's `requires_permission` was denied.
    """

    entitlements: list[ModelEntitlement] = field(default_factory=list)


@dataclass
@PayloadRegistry.register
class ListModelEntitlementsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Model-entitlement listing could not complete.

    Returned when the subject's library or node type cannot be resolved. Callers can
    inspect `result_details` for a human-readable message.

    Args:
        failure_code: Machine-readable reason the subject could not be resolved.
    """

    failure_code: EvaluationFailureCode | None = None
