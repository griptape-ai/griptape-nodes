"""Fact tree backing the `context` axis of permission rules.

Two flavours of fact:

* **Static / event-invalidated** facts published via `register_provider`. The
  provider is a cheap sync callable; the registry caches its result and drops
  the cache when the named invalidator fires (driven by `AppPayload` event
  listeners on `PermissionManager`).
* **Per-request enrichers** registered via `register_request_enricher` that
  produce transient facts scoped to a single request evaluation. These are the
  way managers expose request-scoped state (e.g. parsed metadata of a library
  about to be registered) without inventing new lifecycle events.

The merged fact tree is a dict keyed by dotted path. Rules read it through
the matcher engine using `ContextMatch.facts`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import TYPE_CHECKING, Any

from griptape_nodes.utils.dict_utils import set_dot_value

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import RequestPayload


class FactInvalidator(StrEnum):
    """When a fact's cached value is dropped.

    Each value maps to a formally defined `AppPayload` / `ExecutionPayload`
    that `PermissionManager` listens to.
    """

    NEVER = "never"
    ON_CONFIG_CHANGED = "on_config_changed"
    ON_LIBRARY_LOADED = "on_library_loaded"
    ON_NODE_EXECUTION_BOUNDARY = "on_node_execution_boundary"
    PER_REQUEST = "per_request"


@dataclass
class _FactProvider:
    path: str
    compute: Callable[[], Any]
    invalidator: FactInvalidator
    cached: Any = None
    has_cache: bool = False
    # Bumped on every invalidation so a compute that started before the
    # invalidation cannot commit a stale value after it (see `build_fact_tree`).
    generation: int = 0


@dataclass
class _ProviderSnapshot:
    """Provider state captured under the lock for one `build_fact_tree` call."""

    provider: _FactProvider
    has_cache: bool
    cached: Any
    generation: int


RequestFactEnricher = Callable[["RequestPayload"], dict[str, Any]]


class FactRegistry:
    """Thread-safe registry of fact providers and per-request enrichers."""

    def __init__(self) -> None:
        self._providers: dict[str, _FactProvider] = {}
        self._enrichers: dict[str, list[RequestFactEnricher]] = {}
        self._lock = Lock()

    def register_provider(
        self,
        path: str,
        compute: Callable[[], Any],
        *,
        invalidator: FactInvalidator = FactInvalidator.PER_REQUEST,
    ) -> None:
        """Publish a fact under `path`. `compute` must be cheap and sync."""
        with self._lock:
            self._providers[path] = _FactProvider(path=path, compute=compute, invalidator=invalidator)

    def unregister_provider(self, path: str) -> None:
        with self._lock:
            self._providers.pop(path, None)

    def register_request_enricher(
        self,
        request_type_name: str,
        enricher: RequestFactEnricher,
    ) -> None:
        """Register a per-request fact enricher keyed by request type name.

        The enricher receives the request payload and returns a dict of
        dotted-path -> value entries that are merged under a `request.*`
        prefix in the fact tree for the duration of the evaluation.
        """
        with self._lock:
            self._enrichers.setdefault(request_type_name, []).append(enricher)

    def unregister_request_enricher(
        self,
        request_type_name: str,
        enricher: RequestFactEnricher,
    ) -> None:
        with self._lock:
            handlers = self._enrichers.get(request_type_name)
            if not handlers:
                return
            try:
                handlers.remove(enricher)
            except ValueError:
                return
            if not handlers:
                del self._enrichers[request_type_name]

    def invalidate(self, invalidator: FactInvalidator) -> None:
        """Drop cached values for every provider with the matching invalidator."""
        with self._lock:
            for provider in self._providers.values():
                if provider.invalidator is invalidator:
                    provider.has_cache = False
                    provider.cached = None
                    provider.generation += 1

    def invalidate_all(self) -> None:
        with self._lock:
            for provider in self._providers.values():
                provider.has_cache = False
                provider.cached = None
                provider.generation += 1

    def build_fact_tree(self, request: RequestPayload | None = None) -> dict[str, Any]:
        """Compute the merged fact tree for one rule evaluation.

        `PER_REQUEST` providers are recomputed every call. Other providers use
        their cached value when present. Per-request enrichers for
        ``type(request).__name__`` are merged under the ``request.*`` prefix.
        """
        with self._lock:
            snapshots = [
                _ProviderSnapshot(
                    provider=provider,
                    has_cache=provider.has_cache,
                    cached=provider.cached,
                    generation=provider.generation,
                )
                for provider in self._providers.values()
            ]
            enrichers = list(self._enrichers.get(type(request).__name__, [])) if request is not None else []
        tree: dict[str, Any] = {}
        for snapshot in snapshots:
            provider = snapshot.provider
            if provider.invalidator is FactInvalidator.PER_REQUEST:
                value = _safe_compute(provider.compute)
            elif snapshot.has_cache:
                value = snapshot.cached
            else:
                value = _safe_compute(provider.compute)
                self._commit_cache(provider, value, snapshot.generation)
            set_dot_value(tree, provider.path, value)
        if request is not None:
            for enricher in enrichers:
                contribution = _safe_enrich(enricher, request)
                # Merge each entry under the `request.` prefix individually rather
                # than replacing the whole subtree, so facts published under
                # `request.*` by a provider are not clobbered.
                for key, value in contribution.items():
                    set_dot_value(tree, f"request.{key}", value)
        return tree

    def _commit_cache(self, provider: _FactProvider, value: Any, generation: int) -> None:
        """Store a freshly computed value unless an invalidation raced the compute.

        The compute ran outside the lock, so an `invalidate` call may have bumped
        the provider's generation in the meantime. Committing in that case would
        resurrect a value the caller asked to drop, so skip it and let the next
        `build_fact_tree` recompute.
        """
        with self._lock:
            if provider.generation != generation:
                return
            provider.cached = value
            provider.has_cache = True


def _safe_compute(compute: Callable[[], Any]) -> Any:
    try:
        return compute()
    except Exception:
        # A misbehaving fact provider must never crash policy evaluation; the
        # rule simply sees `None` for that path and matchers that needed it
        # fall through.
        return None


def _safe_enrich(enricher: RequestFactEnricher, request: RequestPayload) -> dict[str, Any]:
    try:
        contribution = enricher(request)
    except Exception:
        return {}
    if not isinstance(contribution, dict):
        return {}
    return contribution
