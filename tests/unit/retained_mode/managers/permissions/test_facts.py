"""Unit tests for the FactRegistry: providers, invalidation, request enrichers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.managers.permissions import FactInvalidator, FactRegistry

_EXPECTED_TWO = 2


@dataclass
class _FakeRequest(RequestPayload):
    """Bare request payload subclass for enricher tests."""

    field_a: str = ""


class TestFactRegistryProviders:
    def test_per_request_provider_recomputes_each_call(self) -> None:
        registry = FactRegistry()
        counter = {"n": 0}

        def compute() -> int:
            counter["n"] += 1
            return counter["n"]

        registry.register_provider("counter", compute, invalidator=FactInvalidator.PER_REQUEST)

        first = registry.build_fact_tree()
        second = registry.build_fact_tree()
        assert first["counter"] == 1
        assert second["counter"] == _EXPECTED_TWO

    def test_cached_provider_does_not_recompute_until_invalidated(self) -> None:
        registry = FactRegistry()
        counter = {"n": 0}

        def compute() -> int:
            counter["n"] += 1
            return counter["n"]

        registry.register_provider("c", compute, invalidator=FactInvalidator.ON_LIBRARY_LOADED)
        first = registry.build_fact_tree()
        second = registry.build_fact_tree()
        assert first["c"] == 1
        assert second["c"] == 1

        registry.invalidate(FactInvalidator.ON_LIBRARY_LOADED)
        third = registry.build_fact_tree()
        assert third["c"] == _EXPECTED_TWO

    def test_dotted_provider_path_nests_into_tree(self) -> None:
        registry = FactRegistry()
        registry.register_provider("loaded_libraries.names", lambda: ["lib-a", "lib-b"])
        tree = registry.build_fact_tree()
        assert tree == {"loaded_libraries": {"names": ["lib-a", "lib-b"]}}

    def test_misbehaving_provider_yields_none_without_crashing(self) -> None:
        registry = FactRegistry()

        def bad() -> int:
            msg = "kaboom"
            raise RuntimeError(msg)

        registry.register_provider("broken", bad)
        registry.register_provider("ok", lambda: "yes")
        tree = registry.build_fact_tree()
        assert tree == {"broken": None, "ok": "yes"}

    def test_unregister_provider_drops_entry(self) -> None:
        registry = FactRegistry()
        registry.register_provider("x", lambda: 1)
        registry.unregister_provider("x")
        assert registry.build_fact_tree() == {}

    def test_invalidate_all_clears_every_cache(self) -> None:
        registry = FactRegistry()
        counter = {"n": 0}

        def compute() -> int:
            counter["n"] += 1
            return counter["n"]

        registry.register_provider("a", compute, invalidator=FactInvalidator.NEVER)
        registry.build_fact_tree()
        registry.invalidate_all()
        registry.build_fact_tree()
        assert counter["n"] == _EXPECTED_TWO

    def test_invalidation_during_compute_is_not_lost(self) -> None:
        """An invalidate that races a compute must drop the freshly computed value.

        The compute runs outside the registry lock, so a concurrent invalidate can
        land between the cache-miss check and the cache write. The generation guard
        means that value is used for the current tree but never committed, so the
        next build recomputes instead of serving a stale cached value.
        """
        registry = FactRegistry()
        counter = {"n": 0}

        def compute() -> int:
            counter["n"] += 1
            if counter["n"] == 1:
                # Simulate an invalidation landing while this compute is in flight.
                registry.invalidate(FactInvalidator.ON_LIBRARY_LOADED)
            return counter["n"]

        registry.register_provider("c", compute, invalidator=FactInvalidator.ON_LIBRARY_LOADED)
        first = registry.build_fact_tree()
        second = registry.build_fact_tree()
        assert first["c"] == 1
        assert second["c"] == _EXPECTED_TWO


class TestFactRegistryEnrichers:
    def test_request_enricher_contributes_under_request_namespace(self) -> None:
        registry = FactRegistry()
        registry.register_request_enricher(
            "_FakeRequest", lambda r: {"foo": "bar", "len_a": len(cast("_FakeRequest", r).field_a)}
        )
        tree = registry.build_fact_tree(_FakeRequest(field_a="hello"))
        assert tree == {"request": {"foo": "bar", "len_a": 5}}

    def test_request_enricher_only_fires_for_matching_type(self) -> None:
        registry = FactRegistry()
        registry.register_request_enricher("_OtherRequest", lambda _: {"x": 1})
        tree = registry.build_fact_tree(_FakeRequest())
        assert "request" not in tree

    def test_request_enricher_failure_is_swallowed(self) -> None:
        registry = FactRegistry()

        def boom(_: RequestPayload) -> dict:
            msg = "nope"
            raise RuntimeError(msg)

        registry.register_request_enricher("_FakeRequest", boom)
        registry.register_request_enricher("_FakeRequest", lambda _: {"x": 1})
        tree = registry.build_fact_tree(_FakeRequest())
        assert tree == {"request": {"x": 1}}

    def test_unregister_enricher(self) -> None:
        registry = FactRegistry()

        def enricher(_: RequestPayload) -> dict:
            return {"x": 1}

        registry.register_request_enricher("_FakeRequest", enricher)
        registry.unregister_request_enricher("_FakeRequest", enricher)
        tree = registry.build_fact_tree(_FakeRequest())
        assert "request" not in tree
