"""Declarative properties and capabilities for libraries and nodes.

Attached to `LibraryMetadata.declarations` and `NodeMetadata.declarations` and
serialized into `griptape_nodes_library.json`.

Each declaration carries exactly one value -- multi-knob behavior splits
into separate declarations rather than wider models. Two categories of
single-value declaration ship today:

* **Properties** state an identity fact about the library or node.
* **Capabilities** state what the library or node can do.

The `LibraryDeclaration` and `NodeDeclaration` unions are scaffolded so
that additional declarations slot in additively without churning the
schema shape.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Sequence

# ---------- Shared enums ----------


class LifecycleStage(StrEnum):
    """Lifecycle stage for a library or node. Shared by library- and node-level properties.

    STABLE is an explicit value (not implied by absence) so library authors must
    make a deliberate choice; this lets consumers flag unstated stage as
    "<No lifecycle stage provided by library author>" rather than silently assuming
    STABLE.

    Node-level semantics:
      - Node with no LifecycleStageNodeProperty -> inherits the library's stage.
      - Node with the property -> overrides the library's stage with the declared value.
    """

    STABLE = "STABLE"
    BETA = "BETA"
    ALPHA = "ALPHA"
    LABS = "LABS"
    DEPRECATED = "DEPRECATED"


class KeySupport(StrEnum):
    """How a node consumes API keys."""

    REQUIRES_CUSTOMER_KEY = "REQUIRES_CUSTOMER_KEY"
    SUPPORTS_CUSTOMER_KEY_OR_GRIPTAPE_KEY = "SUPPORTS_CUSTOMER_KEY_OR_GRIPTAPE_KEY"
    REQUIRES_GRIPTAPE_KEY = "REQUIRES_GRIPTAPE_KEY"


class WorkerCompatibility(StrEnum):
    """Whether a library can run in a worker subprocess.

    Absence of a ``WorkerModeCompatibility`` declaration is treated as
    ``COMPATIBLE``.
    """

    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"


class WorkerMode(StrEnum):
    """Where a worker-compatible library launches by default.

    Only meaningful when the library is also ``WorkerCompatibility.COMPATIBLE``.
    Absence of a ``SuggestedWorkerMode`` declaration is treated as
    ``ORCHESTRATOR``.
    """

    ORCHESTRATOR = "ORCHESTRATOR"
    WORKER = "WORKER"


# ---------- Shared models ----------


class LibraryDependency(BaseModel):
    url: str
    required: bool = True


# ---------- Library-level declarations ----------


class LifecycleStageLibraryProperty(BaseModel):
    """Lifecycle stage that applies to every node in the library.

    Absence of this property means "unstated" -- consumers should surface that
    explicitly rather than defaulting to STABLE.
    """

    type: Literal["lifecycle_stage"] = "lifecycle_stage"
    stage: LifecycleStage


class WorkerModeCompatibility(BaseModel):
    """Declares whether this library is compatible with worker hosting.

    Pair with a ``SuggestedWorkerMode`` to state the author's suggested
    starting point; absence of this declaration is treated as
    ``compatibility=COMPATIBLE``.
    """

    type: Literal["worker_mode_compatibility"] = "worker_mode_compatibility"
    compatibility: WorkerCompatibility


class SuggestedWorkerMode(BaseModel):
    """Declares the author's suggested launch mode (orchestrator vs. worker).

    A starting point, not a hard constraint -- once the GUI override ships,
    users can flip a worker-compatible library between modes. Absence of
    this declaration is treated as "no author suggestion"; consumers apply
    the engine default (today: orchestrator).

    Only meaningful when paired with ``WorkerCompatibility.COMPATIBLE``. A
    ``LibraryMetadata`` validator rejects the contradictory pairing of
    ``INCOMPATIBLE`` with ``mode=WORKER``.
    """

    type: Literal["suggested_worker_mode"] = "suggested_worker_mode"
    mode: WorkerMode


# `Annotated[X | Y, Field(discriminator="type")]` is Pydantic v2's discriminated-union
# idiom. Breakdown:
#   - `X | Y` is the union of valid member classes.
#   - `typing.Annotated[T, extra]` attaches metadata to a type without changing it at
#     runtime; Pydantic reads that metadata to know how to validate and serialize the type.
#   - `Field(discriminator="type")` tells Pydantic: "look at the `type` attribute of each
#     incoming dict to decide which class to build." Each union member must have a
#     `type: Literal[...]` attribute with a distinct string. Unknown `type` values raise
#     ValidationError (strict validation).
# This is the canonical Pydantic v2 way to round-trip "one of several shapes" through JSON.
LibraryDeclaration = Annotated[
    LifecycleStageLibraryProperty | WorkerModeCompatibility | SuggestedWorkerMode,
    Field(discriminator="type"),
]


def requires_worker_process(declarations: Sequence[LibraryDeclaration]) -> bool:
    """Resolve the load-time worker-process decision from a library's declarations.

    A library requires a dedicated worker subprocess when:

    1. It is compatible with worker hosting (``WorkerCompatibility.COMPATIBLE``
       -- absence of a ``WorkerModeCompatibility`` is treated as ``COMPATIBLE``),
       AND
    2. Its suggested launch mode is ``WorkerMode.WORKER``.

    Anything else -- ``INCOMPATIBLE`` capability, no
    ``SuggestedWorkerMode`` at all, or ``ORCHESTRATOR`` suggestion --
    means the library runs in the orchestrator process.

    Centralized here so the future GUI flip updates only one site.
    """
    capability = next((d for d in declarations if isinstance(d, WorkerModeCompatibility)), None)
    if capability is not None and capability.compatibility is WorkerCompatibility.INCOMPATIBLE:
        return False
    suggested = next((d for d in declarations if isinstance(d, SuggestedWorkerMode)), None)
    if suggested is None:
        return False
    return suggested.mode is WorkerMode.WORKER


# ---------- Node-level declarations ----------


class LifecycleStageNodeProperty(BaseModel):
    """Lifecycle stage override for an individual node.

    Absence of this property on a node means "inherit from the library." Presence
    overrides with the declared value. Consumers (UI) resolve inheritance at display
    time; the schema layer stores only what the author wrote.
    """

    type: Literal["lifecycle_stage"] = "lifecycle_stage"
    stage: LifecycleStage


class KeySupportNodeProperty(BaseModel):
    """Declares how this node consumes API keys."""

    type: Literal["key_support"] = "key_support"
    support: KeySupport


# See the comment above `LibraryDeclaration` for how `Annotated[... discriminator ...]` works.
NodeDeclaration = Annotated[
    LifecycleStageNodeProperty | KeySupportNodeProperty,
    Field(discriminator="type"),
]
