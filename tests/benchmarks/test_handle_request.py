"""Benchmarks for the end-to-end request dispatch hot path.

Measures:
- Full handle_request roundtrip (all overhead excluding business logic)
- fields(request) scan for omit_from_result metadata
- inspect.iscoroutinefunction() vs a cached boolean
"""

from __future__ import annotations

import inspect

from griptape_nodes.retained_mode.events.app_events import GetEngineVersionRequest, GetEngineVersionResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


def test_handle_request_roundtrip(benchmark, griptape_nodes):
    """Full handle_request cycle for a lightweight request type.

    GetEngineVersionRequest has trivial business logic, so timing reflects
    the framework overhead: dispatch, flush, _handle_request_core, broadcast check.
    """
    request = GetEngineVersionRequest()

    result = benchmark(GriptapeNodes.handle_request, request)

    assert isinstance(result, GetEngineVersionResultSuccess)


def test_is_coroutinefunction_check(benchmark, griptape_nodes):
    """Cost of inspect.iscoroutinefunction() on every sync handle_request call.

    The sync EventManager.handle_request() calls this on the callback each time.
    This benchmark measures the raw introspection cost vs a cached bool lookup.
    """
    event_mgr = griptape_nodes.EventManager()
    callback = event_mgr._request_type_to_manager.get(type(GetEngineVersionRequest()))

    def check_via_inspect():
        return inspect.iscoroutinefunction(callback)

    is_async = inspect.iscoroutinefunction(callback)

    def check_via_cache():
        return is_async

    # Benchmark the inspect path (current behaviour)
    benchmark(check_via_inspect)


def test_is_coroutinefunction_cached(benchmark, griptape_nodes):
    """Cost of a cached bool lookup — the ceiling for the iscoroutinefunction fix."""
    event_mgr = griptape_nodes.EventManager()
    callback = event_mgr._request_type_to_manager.get(type(GetEngineVersionRequest()))
    is_async = inspect.iscoroutinefunction(callback)

    def check_via_cache():
        return is_async

    benchmark(check_via_cache)


def test_omit_from_result_field_scan(benchmark, griptape_nodes):
    """Cost of dataclasses.fields(request) scan for omit_from_result metadata.

    Called in _handle_request_core for every request. Only one field in the
    entire codebase uses this metadata flag, yet every request pays the scan cost.
    """
    from dataclasses import fields

    request = GetEngineVersionRequest()

    def scan_fields():
        for f in fields(request):
            if f.metadata.get("omit_from_result", False):
                pass

    benchmark(scan_fields)
