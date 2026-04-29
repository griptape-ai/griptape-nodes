"""Benchmarks for BaseNode.parameters property — a recursive DFS tree walk.

The `parameters` property calls find_elements_by_type(Parameter) on every access,
which recursively walks the entire element tree. It is called in multiple hot paths
per node operation with no caching.

Parametrized over [5, 20, 50] parameters.
"""

from __future__ import annotations

import pytest

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode


class _BenchNode(BaseNode):
    def run(self) -> None:
        pass

    def initialize(self) -> None:
        pass

    def process(self) -> None:
        return None


def _build_flat_node(param_count: int) -> BaseNode:
    """Node with `param_count` flat (non-nested) parameters."""
    node = _BenchNode(name="bench_flat")
    for i in range(param_count):
        p = Parameter(
            name=f"param_{i}",
            input_types=["str"],
            output_type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )
        node.root_ui_element.add_child(p)
    return node


@pytest.fixture(params=[5, 20, 50])
def flat_node(request, griptape_nodes):
    return _build_flat_node(request.param), request.param


def test_parameters_property_flat(benchmark, flat_node):
    """Cost of BaseNode.parameters on a flat element tree.

    Each call walks root_ui_element._children and isinstance-checks every item.
    Even for a flat tree this is O(n) in the number of parameters.
    """
    node, count = flat_node

    result = benchmark(lambda: node.parameters)

    assert len(result) == count


def test_find_elements_by_type_flat(benchmark, flat_node):
    """Direct cost of find_elements_by_type — the method backing the property."""
    node, count = flat_node

    result = benchmark(node.root_ui_element.find_elements_by_type, Parameter)

    assert len(result) == count
