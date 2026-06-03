"""Declarative properties and capabilities for libraries and nodes.

Attached to `LibraryMetadata.declarations` and `NodeMetadata.declarations` and
serialized into `griptape_nodes_library.json`.

Two declaration categories ship today:

* **Properties** are identity facts ("I am BETA", "I require a customer key").
* **Capabilities** describe how a library wants to be hosted or executed
  (e.g. `WorkerLibraryCapability` for orchestrator vs. worker process).

The `LibraryDeclaration` and `NodeDeclaration` unions are scaffolded so that
additional categories (further capabilities, requirements, etc.) can slot in
additively without churning the schema shape.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

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


class WorkerSupport(StrEnum):
    """How a library wants to be hosted across orchestrator vs. worker processes.

    Absence of a WorkerLibraryCapability means REQUIRES_ORCHESTRATOR_MODE;
    consumers default at the call site rather than the schema synthesizing an
    implicit instance.
    """

    SUPPORTS_WORKER_MODE = "SUPPORTS_WORKER_MODE"
    REQUIRES_ORCHESTRATOR_MODE = "REQUIRES_ORCHESTRATOR_MODE"
    REQUIRES_WORKER_MODE = "REQUIRES_WORKER_MODE"


# ---------- Library-level declarations ----------


class LifecycleStageLibraryProperty(BaseModel):
    """Lifecycle stage that applies to every node in the library.

    Absence of this property means "unstated" -- consumers should surface that
    explicitly rather than defaulting to STABLE.
    """

    type: Literal["lifecycle_stage"] = "lifecycle_stage"
    stage: LifecycleStage


class WorkerLibraryCapability(BaseModel):
    """Declares how this library can be hosted (orchestrator vs. worker process).

    Worker hosting is modeled as a capability (rather than a property) so that
    additional worker-execution knobs (e.g. concurrency) can attach to this same
    declaration without inventing a parallel category.

    Absence means REQUIRES_ORCHESTRATOR_MODE; consumers default at the call site.
    Today the engine maps SUPPORTS_WORKER_MODE to in-process; the GUI flip lands later.
    """

    type: Literal["worker"] = "worker"
    support: WorkerSupport

    def requires_worker_process(self) -> bool:
        """Map the declared support to today's load-time `requires_worker` bool.

        Centralized here so the future GUI flip for SUPPORTS_WORKER_MODE updates
        only one site.
        """
        return self.support is WorkerSupport.REQUIRES_WORKER_MODE


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
# A single-member union is still wrapped in this idiom because future declaration types
# (capabilities, requirements) slot in additively without changing the field's shape.
LibraryDeclaration = Annotated[
    LifecycleStageLibraryProperty | WorkerLibraryCapability,
    Field(discriminator="type"),
]


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
