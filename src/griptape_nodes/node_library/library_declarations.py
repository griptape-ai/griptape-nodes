"""Declarative property types for libraries and nodes.

These are attached to `LibraryMetadata.properties` and `NodeMetadata.properties`
and serialized into `griptape_nodes_library.json`.

Summary of the model:
  - `PermissionCatalogLibraryProperty` declares a library's permission vocabulary.
    The effective catalog = engine built-ins (permission_builtins.BUILTIN_PERMISSIONS)
    plus this library's `permissions` dict.
  - `ModelCatalogLibraryProperty` declares third-party model entitlements once, keyed
    by short name. Nodes reference entitlements via `ModelUsageNodeProperty(name=...)`.
  - `RequiredPermissionsLibraryProperty` / `RequiredPermissionsNodeProperty` gate the
    whole library or whole node by naming permissions from the effective catalog.
  - Marker properties (`ExecuteArbitraryCodeNodeProperty`, `ProxyModelNodeProperty`,
    `EngineControlNodeProperty`) are pure capability manifests. The engine ships a
    default `marker_mapping` (see `permission_builtins`); libraries can override.

Runtime permission evaluation lives in `permissions_manager.py`. Catalog
reference validation lives in `library_validation.validate_library_declarations`
and runs during library load.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ---------- Shared enums ----------


class ProductionStatus(StrEnum):
    """Lifecycle status for a library or node. Shared by library- and node-level properties.

    PRODUCTION is an explicit value (not implied by absence) so library authors must
    make a deliberate choice; this lets consumers flag unstated status as
    "<No production status provided by library author>" rather than silently assuming
    PRODUCTION.

    Node-level semantics:
      - Node with no ProductionStatusNodeProperty -> inherits the library's status.
      - Node with the property -> overrides the library's status with the declared value.
    """

    PRODUCTION = "PRODUCTION"
    BETA = "BETA"
    ALPHA = "ALPHA"
    EXPERIMENTAL = "EXPERIMENTAL"


class KeySupport(StrEnum):
    """How a node consumes API keys."""

    REQUIRES_CUSTOMER_KEY = "REQUIRES_CUSTOMER_KEY"
    SUPPORTS_CUSTOMER_KEY_OR_GRIPTAPE_KEY = "SUPPORTS_CUSTOMER_KEY_OR_GRIPTAPE_KEY"
    REQUIRES_GRIPTAPE_KEY = "REQUIRES_GRIPTAPE_KEY"


# ---------- Shared helper types ----------


class PermissionDeclaration(BaseModel):
    """A single permission entry in a library's catalog.

    The permission *name* is the dict key in `PermissionCatalogLibraryProperty.permissions`;
    that's what node authors reference from `requires_permission` fields or
    `RequiredPermissions*.names` lists.

    Fields:
      - description: required. Human-readable explanation surfaced in admin UIs and error
        messages ("Access Kling video generation models").
      - policies: a list of Cedar policy statements (source text) that govern when
        this permission is granted. Each entry is a single Cedar `permit` or
        `forbid` statement as authors would write it in a .cedar file. The engine
        stores and round-trips these strings; the Cedar evaluator will parse and
        apply them when it ships. Cedar syntax validation at library-load time is
        planned (see `library_validation.py` for the current validation surface).
    """

    description: str
    policies: list[str] = Field(default_factory=list)


class ModelEntitlement(BaseModel):
    """A right to call a third-party model, declared once at the library level.

    Nodes reference an entitlement by short name via `ModelUsageNodeProperty(name=...)`.
    Declaring model entitlements centrally prevents drift (27 nodes using Kling v2 all
    reference the same terms_url) and keeps node-level declarations terse.

    An entitlement bundles two concerns: identifying fields that describe the model
    (display_name, provider, family, model, terms_url) and the permission gate that
    grants access (requires_permission).

    Fields:
      - display_name: required. Label shown in UIs (dropdowns, badges, errors).
      - provider: required. Upstream vendor or service ("Kling", "OpenAI").
      - family: optional. Grouping within the provider ("Kling v2", "GPT-4").
      - model: optional. Exact model identifier ("kling-v2-master", "gpt-4o-mini").
      - terms_url: required. Canonical T&C URL.
      - requires_permission: optional. References a name in the effective permission
        catalog (library's catalog plus engine built-ins). When null, any caller who
        reaches the entitlement can use it; when set, the permissions manager gates
        access on the named permission.
    """

    display_name: str
    provider: str
    family: str | None = None
    model: str | None = None
    terms_url: str
    requires_permission: str | None = None


# ---------- Library-level properties ----------


class ProductionStatusLibraryProperty(BaseModel):
    """Production-lifecycle status that applies to every node in the library.

    Absence of this property means "unstated" -- consumers should surface that
    explicitly rather than defaulting to PRODUCTION.
    """

    type: Literal["production_status"] = "production_status"
    status: ProductionStatus


class PermissionCatalogLibraryProperty(BaseModel):
    """Declares the named permissions this library uses, plus optional marker shortcuts.

    Effective permission catalog = engine built-ins (see permission_builtins.py) plus
    this library's `permissions`. Every `requires_permission` / `names` reference in
    the library must resolve against the effective catalog. Libraries may not redeclare
    a built-in permission name (shadowing is rejected at load time).

    Cross-library collision policy: names are bare. If library A and library B both
    declare `use_kling`, admin policies against that name apply to both. Libraries
    wanting isolation self-prefix (e.g. `mylib_use_kling`).

    `marker_mapping` overlays on top of the engine's default marker_mapping. Built-in
    defaults:
        execute_arbitrary_code -> run_arbitrary_python
        engine_control         -> access_engine
        proxy_model            -> use_proxy_model
    Libraries rarely need to set this. Authors can override a default (routing a marker
    to a library-specific permission) or add mappings for markers that don't have a
    built-in default. Every mapping value must resolve against the effective catalog.
    """

    type: Literal["permission_catalog"] = "permission_catalog"
    permissions: dict[str, PermissionDeclaration] = Field(default_factory=dict)
    marker_mapping: dict[str, str] = Field(default_factory=dict)


class ModelCatalogLibraryProperty(BaseModel):
    """Library-level catalog of model entitlements.

    Each entry in `entitlements` is a named `ModelEntitlement` that nodes can reference
    via `ModelUsageNodeProperty(name=...)`. Declaring entitlements centrally prevents
    drift and keeps node definitions terse.
    """

    type: Literal["model_catalog"] = "model_catalog"
    entitlements: dict[str, ModelEntitlement]


class RequiredPermissionsLibraryProperty(BaseModel):
    """All listed permissions must be granted for the library to be used.

    Each name must resolve against the effective permission catalog. AND semantics
    across the list: every name must be granted. Authors needing OR semantics
    should split the gate across separate library-level or node-level declarations.

    The engine surfaces missing permissions to the caller so clients can describe
    which entitlements are needed.
    """

    type: Literal["required_permissions"] = "required_permissions"
    names: list[str]


# `Annotated[X | Y, Field(discriminator="type")]` is Pydantic v2's discriminated-union
# idiom. Breakdown:
#   - `X | Y` is the union of valid member classes.
#   - `typing.Annotated[T, extra]` attaches metadata to a type without changing it at
#     runtime; Pydantic reads that metadata to know how to validate and serialize the type.
#   - `Field(discriminator="type")` tells Pydantic: "look at the `type` attribute of each
#     incoming dict to decide which class to build." Each union member must have a
#     `type: Literal[...]` attribute with a distinct string. Unknown `type` values raise
#     ValidationError (strict validation).
# Wherever this alias is used in a `list[...]` field, Pydantic applies the discriminator
# per-element. This is the canonical way to serialize "one of several shapes" in JSON.
LibraryProperty = Annotated[
    ProductionStatusLibraryProperty
    | PermissionCatalogLibraryProperty
    | ModelCatalogLibraryProperty
    | RequiredPermissionsLibraryProperty,
    Field(discriminator="type"),
]


# ---------- Node-level properties ----------


class ProductionStatusNodeProperty(BaseModel):
    """Production-lifecycle status override for an individual node.

    Absence of this property on a node means "inherit from the library." Presence
    overrides with the declared value. Consumers (UI) resolve inheritance at display
    time; the schema layer stores only what the author wrote.
    """

    type: Literal["production_status"] = "production_status"
    status: ProductionStatus


class RequiredPermissionsNodeProperty(BaseModel):
    """All listed permissions must be granted for this node to be used.

    Every name must resolve against the effective permission catalog. AND semantics
    across the list: every name must be granted.

    This is the canonical way to gate a node on permissions. Per-option gating on
    other properties (e.g. `ModelUsageNodeProperty` via the entitlement's
    `requires_permission`) is informational; node code dispatches a
    `ListModelEntitlementsRequest` to get the permitted subset. The engine surfaces
    missing permissions to the caller so clients can describe which entitlements are
    needed.
    """

    type: Literal["required_permissions"] = "required_permissions"
    names: list[str]


class ModelUsageNodeProperty(BaseModel):
    """Reference to a model entitlement declared at the library level.

    Nodes don't carry provider/family/terms_url directly. They reference a named entry
    in the library's `ModelCatalogLibraryProperty.entitlements`; every field
    (display_name, provider, family, model, terms_url, requires_permission) is resolved
    from that entitlement.

    Load-time validation: `name` must resolve to a declared entitlement. Unresolved
    names fail library registration.

    Multi-provider nodes (e.g. an Agent with multiple backends) carry one reference
    per entitlement. To get the subset of entitlements the caller is permitted to use,
    dispatch a `ListModelEntitlementsRequest` to the `PermissionsManager`.
    """

    type: Literal["model_usage"] = "model_usage"
    name: str


class ProxyModelNodeProperty(BaseModel):
    """Marker: node calls a proxy model endpoint."""

    type: Literal["proxy_model"] = "proxy_model"


class ExecuteArbitraryCodeNodeProperty(BaseModel):
    """Marker: node executes arbitrary user-supplied code."""

    type: Literal["execute_arbitrary_code"] = "execute_arbitrary_code"


class EngineControlNodeProperty(BaseModel):
    """Marker: node exposes direct engine access."""

    type: Literal["engine_control"] = "engine_control"


class KeySupportNodeProperty(BaseModel):
    """Declares how this node consumes API keys."""

    type: Literal["key_support"] = "key_support"
    support: KeySupport


# See the comment above `LibraryProperty` for how `Annotated[... discriminator ...]` works.
NodeProperty = Annotated[
    ProductionStatusNodeProperty
    | RequiredPermissionsNodeProperty
    | ModelUsageNodeProperty
    | ProxyModelNodeProperty
    | ExecuteArbitraryCodeNodeProperty
    | EngineControlNodeProperty
    | KeySupportNodeProperty,
    Field(discriminator="type"),
]
