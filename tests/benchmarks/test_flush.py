"""Benchmarks for _flush_tracked_parameter_changes.

This method is called after every request (sync and async). It iterates all
objects in ObjectManager looking for BaseNodes with dirty tracked parameters.

Key question: what does the common case (nothing dirty) cost at scale?

Parametrized over [10, 50, 100] nodes via `populated_object_manager_for_flush`.
"""

from __future__ import annotations

from griptape_nodes.retained_mode.managers.event_manager import EventManager


def test_flush_no_dirty_nodes(benchmark, populated_object_manager_for_flush, griptape_nodes):
    """Cost of _flush_tracked_parameter_changes when zero nodes have dirty parameters.

    This is the overwhelmingly common case — most requests don't change any
    parameters, yet the flush still scans all nodes every time.
    """
    _obj_mgr, nodes, _count = populated_object_manager_for_flush
    event_mgr: EventManager = griptape_nodes.EventManager()

    # Confirm no nodes are dirty before benchmarking
    for node in nodes:
        assert not node._tracked_parameters

    benchmark(event_mgr._flush_tracked_parameter_changes, _obj_mgr)


def test_flush_some_dirty_nodes(benchmark, populated_object_manager_for_flush, griptape_nodes):
    """Cost when ~10% of nodes have dirty tracked parameters.

    Simulates a realistic mid-execution state where some nodes have pending
    parameter change events to emit.
    """
    from unittest.mock import MagicMock

    _obj_mgr, nodes, count = populated_object_manager_for_flush
    event_mgr: EventManager = griptape_nodes.EventManager()
    dirty_count = max(1, count // 10)

    # Use a MagicMock so _emit_alter_element_event_if_possible() is a no-op
    mock_param = MagicMock()

    def run_flush():
        # Re-mark nodes dirty before each iteration (flush clears them)
        for node in nodes[:dirty_count]:
            node._tracked_parameters.append(mock_param)
        event_mgr._flush_tracked_parameter_changes(_obj_mgr)

    benchmark(run_flush)
