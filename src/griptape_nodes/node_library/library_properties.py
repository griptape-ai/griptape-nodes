"""Declarative property types for libraries and nodes.

These are attached to `LibraryMetadata.properties` and `NodeMetadata.properties`
and serialized into `griptape_nodes_library.json`. v1 is declaration-only: the
data is exposed through existing metadata events so external tools and the UI
can inspect capabilities / compliance without installing the library, but
nothing here is enforced at runtime.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


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


# ---------- Library-level properties ----------


class ProductionStatusLibraryProperty(BaseModel):
    """Production-lifecycle status that applies to every node in the library.

    Absence of this property means "unstated" -- consumers should surface that
    explicitly rather than defaulting to PRODUCTION.
    """

    type: Literal["production_status"] = "production_status"
    status: ProductionStatus


class RequiredPermissionsLibraryProperty(BaseModel):
    """Cedar-style permissions required to SEE / INSTALL / USE this library.

    v1 is a declarative manifest only; there is no evaluator.
    """

    type: Literal["required_permissions"] = "required_permissions"
    permissions: dict[str, str]


# `Annotated[X | Y, Field(discriminator="type")]` is Pydantic v2's discriminated-union
# idiom. Breakdown:
#   - `X | Y` is the union of valid member classes.
#   - `typing.Annotated[T, extra]` attaches metadata to a type without changing it at
#     runtime; Pydantic reads that metadata to tell how to validate and serialize the type.
#   - `Field(discriminator="type")` tells Pydantic: "look at the `type` attribute of each
#     incoming dict to decide which class to build." Each union member must have a
#     `type: Literal[...]` attribute with a distinct string. Unknown `type` values raise
#     ValidationError (this is what gives us strict-for-v1 behavior).
# Wherever this alias is used in a `list[...]` field, Pydantic applies the discriminator
# per-element. This is the canonical way to serialize "one of several shapes" in JSON.
LibraryProperty = Annotated[
    ProductionStatusLibraryProperty | RequiredPermissionsLibraryProperty,
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
    """Cedar-style permissions required to SEE / USE this node."""

    type: Literal["required_permissions"] = "required_permissions"
    permissions: dict[str, str]


class ModelUsageNodeProperty(BaseModel):
    """Node uses a third-party model, declared at the most specific level the author knows.

    Authors declare the provider (always), and optionally the family and specific model.
    If a node calls out to multiple providers (e.g. an Agent that can use either
    Anthropic or OpenAI), add one `model_usage` property per provider.

    Fields:
      - provider: required. The upstream vendor or service (e.g. "Anthropic", "Kling",
        "OpenAI"). Answers "no Kling"-style admin policies directly.
      - family: optional. A grouping within the provider (e.g. "Claude 4", "Kling v2",
        "GPT-4"). Null when the node routes dynamically within a provider.
      - model: optional. The exact model identifier (e.g. "claude-opus-4-7", "gpt-4o-mini").
        Null when the specific model is selected at runtime.
      - terms_url: required. Canonical T&C URL for this provider's usage of this node.

    All three granularity fields live in one object so provider/family/model can't drift
    apart across edits. Admin filters query any level uniformly:
        property.provider == "Kling"           # blanket: no Kling at all
        property.family   == "Kling v2"        # "no Kling v2 specifically"
        property.model    == "gpt-4o-mini"     # "only allow gpt-4o-mini"
    """

    type: Literal["model_usage"] = "model_usage"
    provider: str
    family: str | None = None
    model: str | None = None
    terms_url: str


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
