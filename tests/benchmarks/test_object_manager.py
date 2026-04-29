"""Benchmarks for ObjectManager lookup and scan operations.

The primary concern is get_filtered_subset(type=BaseNode), which is an O(n)
linear scan called after EVERY request in _flush_tracked_parameter_changes.

Parametrized over [10, 50, 100, 500] nodes via `populated_object_manager` fixture.
"""

from __future__ import annotations

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode


def test_get_filtered_subset_nodes(benchmark, populated_object_manager):
    """O(n) scan cost of get_filtered_subset(type=BaseNode).

    This is the dominant cost in _flush_tracked_parameter_changes, called
    after every single request regardless of whether any parameters changed.
    """
    obj_mgr, count = populated_object_manager

    result = benchmark(obj_mgr.get_filtered_subset, type=BaseNode)

    assert len(result) == count


def test_get_filtered_subset_flows(benchmark, populated_object_manager):
    """O(n) scan cost of get_filtered_subset(type=ControlFlow).

    Used in clear_data() and workflow loading paths.
    """
    obj_mgr, _count = populated_object_manager

    result = benchmark(obj_mgr.get_filtered_subset, type=ControlFlow)

    assert len(result) == 5  # noqa: PLR2004


def test_attempt_get_object_by_name(benchmark, populated_object_manager):
    """O(1) dict lookup — confirms name-based access stays fast as object count grows."""
    obj_mgr, count = populated_object_manager
    target_name = f"node_{count // 2}"

    result = benchmark(obj_mgr.attempt_get_object_by_name, target_name)

    assert result is not None
