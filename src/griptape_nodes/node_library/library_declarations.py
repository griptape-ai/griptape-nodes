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
from typing import TYPE_CHECKING, Annotated, Literal, NamedTuple

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

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
    NO_KEY_REQUIRED = "NO_KEY_REQUIRED"


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


# ---------- Model catalog (provider -> family -> model) ----------


class ModelOffering(BaseModel):
    """A single model the library offers. Leaf of the catalog.

    Identified by its parent dict key, not by a field on this class -- the
    key is the stable handle that admin policies and node references use.
    Multiple offerings can describe the same upstream `model` value with
    different `key_support`; they appear as two dict entries with two keys.

    `notes` is free-form author guidance surfaced alongside the offering in
    UIs and admin tooling (e.g. "BYOK requires injecting a provider-specific
    prompt driver"). Use it for caveats that don't fit other fields.
    """

    display_name: str
    model: str | None = None
    key_support: KeySupport
    terms_url: str | None = None
    notes: str | None = None


class ModelFamily(BaseModel):
    """A family within a provider (e.g. 'Claude 4', 'GPT-4'). Optional layer.

    Providers without meaningful families put their offerings directly under
    the provider's `offerings` dict.

    `notes` is free-form author guidance applying to every offering in the
    family (e.g. an explanation of how the family is positioned vs. the
    provider's other families). Per-offering `notes` are additive.

    `key_support` declared here describes a default for the family. Per-offering
    `key_support` is required and overrides the family value; the family value is
    informational (admin-policy hint, default for future offerings).
    """

    display_name: str
    terms_url: str | None = None
    notes: str | None = None
    key_support: KeySupport | None = None
    offerings: dict[str, ModelOffering] = Field(default_factory=dict)


class ModelProvider(BaseModel):
    """A model provider (e.g. 'Anthropic', 'OpenAI', 'Kling').

    `notes` is free-form author guidance applying to every family/offering
    under the provider (e.g. "BYOK requires injecting a provider-specific
    prompt driver"). Lower-level `notes` are additive.

    `key_support` declared here describes a default for everything under the
    provider. It is most useful when the provider has no offerings at all
    (e.g. a dynamic-runtime provider like Ollama where `key_support=NO_KEY_REQUIRED`
    is the only meaningful signal); it also carries through as a default for
    any family or offering that doesn't override.
    """

    display_name: str
    terms_url: str | None = None
    notes: str | None = None
    key_support: KeySupport | None = None
    families: dict[str, ModelFamily] = Field(default_factory=dict)
    offerings: dict[str, ModelOffering] = Field(default_factory=dict)


class ModelCatalogLibraryProperty(BaseModel):
    """Library-level declaration of available models, organized by provider/family/model."""

    type: Literal["model_catalog"] = "model_catalog"
    providers: dict[str, ModelProvider] = Field(default_factory=dict)


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
    LifecycleStageLibraryProperty | WorkerModeCompatibility | SuggestedWorkerMode | ModelCatalogLibraryProperty,
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


class ResolvedOffering(NamedTuple):
    """An offering paired with its parent provider/family identifiers.

    `family_id` is None when the offering hangs directly off a provider's
    top-level `offerings` dict.
    """

    provider_id: str
    family_id: str | None
    offering_id: str
    offering: ModelOffering
    provider: ModelProvider
    family: ModelFamily | None


def iter_catalog_offerings(catalog: ModelCatalogLibraryProperty) -> Iterator[ResolvedOffering]:
    """Yield every offering in the catalog with its parent context.

    Walks both the family-nested offerings and the provider-direct offerings.
    Order: provider insertion order, then family insertion order, then
    offering insertion order within each container.
    """
    for provider_id, provider in catalog.providers.items():
        for family_id, family in provider.families.items():
            for offering_id, offering in family.offerings.items():
                yield ResolvedOffering(
                    provider_id=provider_id,
                    family_id=family_id,
                    offering_id=offering_id,
                    offering=offering,
                    provider=provider,
                    family=family,
                )
        for offering_id, offering in provider.offerings.items():
            yield ResolvedOffering(
                provider_id=provider_id,
                family_id=None,
                offering_id=offering_id,
                offering=offering,
                provider=provider,
                family=None,
            )


def resolve_terms_url(catalog: ModelCatalogLibraryProperty, offering_id: str) -> str | None:
    """Resolve an offering's effective TOS URL, cascading most-specific-wins.

    Resolution order:
      1. The offering's own `terms_url`, if set.
      2. The parent family's `terms_url`, if set.
      3. The parent provider's `terms_url`, if set.
      4. None -- consumers should surface "no TOS declared" rather than
         silently defaulting.

    Returns None if the offering id does not resolve to any offering in the
    catalog. Use validation (`validate_library_declarations`) to detect that
    case at library load; `resolve_terms_url` is meant for runtime queries
    where the catalog is already trusted.
    """
    for resolved in iter_catalog_offerings(catalog):
        if resolved.offering_id != offering_id:
            continue
        if resolved.offering.terms_url is not None:
            return resolved.offering.terms_url
        if resolved.family is not None and resolved.family.terms_url is not None:
            return resolved.family.terms_url
        return resolved.provider.terms_url
    return None


def resolve_key_support(catalog: ModelCatalogLibraryProperty, offering_id: str) -> KeySupport | None:
    """Resolve an offering's effective key_support, cascading most-specific-wins.

    Resolution order:
      1. The offering's own `key_support` (always set on offerings).
      2. The parent family's `key_support`, if set.
      3. The parent provider's `key_support`, if set.
      4. None -- only reachable for an unknown offering id.

    Returns None if the offering id does not resolve to any offering in the
    catalog. Use validation (`validate_library_declarations`) to detect that
    case at library load.
    """
    for resolved in iter_catalog_offerings(catalog):
        if resolved.offering_id != offering_id:
            continue
        # Offerings always declare key_support; the cascade exists for
        # provider-only declarations (e.g. Ollama with no offerings).
        return resolved.offering.key_support
    return None


# ---------- Node-level declarations ----------


class LifecycleStageNodeProperty(BaseModel):
    """Lifecycle stage override for an individual node.

    Absence of this property on a node means "inherit from the library." Presence
    overrides with the declared value. Consumers (UI) resolve inheritance at display
    time; the schema layer stores only what the author wrote.
    """

    type: Literal["lifecycle_stage"] = "lifecycle_stage"
    stage: LifecycleStage


class ModelUsageNodeProperty(BaseModel):
    """References specific model offerings the node uses, by their catalog dict keys.

    Each entry must resolve to an offering somewhere in the library's
    `ModelCatalogLibraryProperty` (validated at library load).

    Use this when the node binds to a specific, named set of offerings. For
    nodes that dynamically enumerate everything in a family or provider at
    runtime, see `ModelFamilyUsageNodeProperty` and `ModelProviderUsageNodeProperty`.
    """

    type: Literal["model_usage"] = "model_usage"
    offering_ids: list[str]


class FamilyReference(BaseModel):
    """A reference to a single family within a provider.

    Family ids are scoped within a provider (the same family id can appear under
    different providers), so a reference must carry both pieces.
    """

    provider_id: str
    family_id: str


class ModelFamilyUsageNodeProperty(BaseModel):
    """References whole model families the node uses.

    Use this when a node dynamically enumerates every offering in one or more
    families at runtime. Each entry must resolve to a family that exists under
    its named provider in the library's `ModelCatalogLibraryProperty`
    (validated at library load).
    """

    type: Literal["model_family_usage"] = "model_family_usage"
    families: list[FamilyReference]


class ModelProviderUsageNodeProperty(BaseModel):
    """References whole providers the node uses.

    Use this when a node dynamically enumerates every offering across an
    entire provider at runtime. Each entry must resolve to a provider declared
    in the library's `ModelCatalogLibraryProperty` (validated at library load).
    """

    type: Literal["model_provider_usage"] = "model_provider_usage"
    provider_ids: list[str]


# See the comment above `LibraryDeclaration` for how `Annotated[... discriminator ...]` works.
NodeDeclaration = Annotated[
    LifecycleStageNodeProperty | ModelUsageNodeProperty | ModelFamilyUsageNodeProperty | ModelProviderUsageNodeProperty,
    Field(discriminator="type"),
]
