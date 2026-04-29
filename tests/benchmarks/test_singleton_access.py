"""Benchmarks for GriptapeNodes singleton manager resolution overhead.

Every call to GriptapeNodes.SomeManager() goes through:
  GriptapeNodes.get_instance() → SingletonMeta.__call__ → cls._instances[cls] dict lookup

_handle_request_core alone resolves OperationDepthManager + WorkflowManager per request.
The async path adds ObjectManager. This adds up across hundreds of requests per execution.
"""

from __future__ import annotations

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


def test_get_instance(benchmark, griptape_nodes):
    """Raw cost of GriptapeNodes.get_instance() — the base of every manager access."""
    benchmark(GriptapeNodes.get_instance)


def test_manager_access_chain(benchmark, griptape_nodes):
    """Cost of the three manager accesses that happen in every handle_request call.

    _handle_request_core resolves OperationDepthManager and WorkflowManager.
    _flush_tracked_parameter_changes resolves ObjectManager.
    This benchmark measures their combined overhead per request cycle.
    """

    def access_chain():
        GriptapeNodes.OperationDepthManager()
        GriptapeNodes.WorkflowManager()
        GriptapeNodes.ObjectManager()

    benchmark(access_chain)


def test_direct_reference_access(benchmark, griptape_nodes):
    """Ceiling: resolve managers once and access via local reference.

    Shows the maximum possible speedup from caching manager references
    instead of re-resolving via get_instance() on every call.
    """
    op_mgr = griptape_nodes.OperationDepthManager()
    wf_mgr = griptape_nodes.WorkflowManager()
    obj_mgr = griptape_nodes.ObjectManager()

    def access_direct():
        _ = op_mgr
        _ = wf_mgr
        _ = obj_mgr

    benchmark(access_direct)
