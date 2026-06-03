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

from pydantic import BaseModel, Field, model_validator

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
    """What hosting modes a library is capable of running under.

    Capability ("can it run as a worker?"), not configuration ("where does it
    launch?"). The launch decision lives in `WorkerLibraryCapability.default_mode`
    and -- once it ships -- the GUI override.

    Absence of a WorkerLibraryCapability is treated as `BOTH` with no
    `default_mode` set; consumers apply the orchestrator default at the call site.
    """

    BOTH = "BOTH"
    ORCHESTRATOR_ONLY = "ORCHESTRATOR_ONLY"


class WorkerMode(StrEnum):
    """Where the library actually launches when the engine starts.

    Configuration ("where do I launch?"), not capability ("can I launch there?").
    Only meaningful when paired with `WorkerSupport.BOTH`.
    """

    ORCHESTRATOR = "ORCHESTRATOR"
    WORKER = "WORKER"


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

    Two axes:

    * `support` -- what the library is capable of (`BOTH` or `ORCHESTRATOR_ONLY`).
    * `default_mode` -- where the library launches when nothing else overrides
      (the future GUI override is the "something else"). `None` means the engine
      picks: today that's orchestrator.

    Absence of the entire declaration is treated as `support=BOTH` with no
    `default_mode` -- equivalent to declaring it explicitly with those values.
    """

    type: Literal["worker"] = "worker"
    support: WorkerSupport = WorkerSupport.BOTH
    default_mode: WorkerMode | None = None

    @model_validator(mode="after")
    def _validate_default_mode_against_support(self) -> WorkerLibraryCapability:
        if self.support is WorkerSupport.ORCHESTRATOR_ONLY and self.default_mode is WorkerMode.WORKER:
            msg = "WorkerLibraryCapability cannot set default_mode=WORKER when support=ORCHESTRATOR_ONLY."
            raise ValueError(msg)
        return self

    def requires_worker_process(self) -> bool:
        """Map the declared capability and default to today's load-time `requires_worker` bool.

        Centralized here so the future GUI flip updates only one site.
        """
        if self.support is WorkerSupport.ORCHESTRATOR_ONLY:
            return False
        return self.default_mode is WorkerMode.WORKER


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
