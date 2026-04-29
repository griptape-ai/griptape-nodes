"""Shared fixtures for performance benchmarks."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

import griptape_nodes.retained_mode.managers.config_manager as config_manager_module
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils.metaclasses import SingletonMeta


@pytest.fixture(autouse=True)
def isolate_user_config() -> Generator[Path, None, None]:
    """Isolate config and singleton state between benchmarks."""
    SingletonMeta._instances.clear()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_config_path = Path(temp_dir) / "griptape_nodes_config.json"
        temp_config_path.write_text(json.dumps({}, indent=2))

        with patch.object(config_manager_module, "USER_CONFIG_PATH", temp_config_path):
            yield temp_config_path

            SingletonMeta._instances.clear()


@pytest.fixture
def griptape_nodes() -> GriptapeNodes:
    return GriptapeNodes()


class _BenchNode(BaseNode):
    """Minimal concrete node for benchmarks — no external dependencies."""

    def run(self) -> None:
        pass

    def initialize(self) -> None:
        pass

    def process(self) -> None:
        return None


@pytest.fixture
def object_manager(griptape_nodes: GriptapeNodes):
    return griptape_nodes.ObjectManager()


@pytest.fixture(params=[10, 50, 100, 500])
def populated_object_manager(request, griptape_nodes: GriptapeNodes):
    """ObjectManager pre-populated with `count` BaseNodes and 5 ControlFlows."""
    from griptape_nodes.exe_types.flow import ControlFlow

    obj_mgr = griptape_nodes.ObjectManager()
    count = request.param

    for i in range(count):
        node = _BenchNode(name=f"node_{i}")
        obj_mgr.add_object_by_name(node.name, node)

    for i in range(5):
        flow = ControlFlow(name=f"flow_{i}")
        obj_mgr.add_object_by_name(flow.name, flow)

    return obj_mgr, count


@pytest.fixture(params=[10, 50, 100])
def populated_object_manager_for_flush(request, griptape_nodes: GriptapeNodes):
    """ObjectManager pre-populated with nodes for flush benchmarks."""
    obj_mgr = griptape_nodes.ObjectManager()
    count = request.param
    nodes = []

    for i in range(count):
        node = _BenchNode(name=f"node_{i}")
        obj_mgr.add_object_by_name(node.name, node)
        nodes.append(node)

    return obj_mgr, nodes, count
