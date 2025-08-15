from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import networkx as nx

from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from concurrent.futures import Future

    from griptape_nodes.exe_types.node_types import BaseNode


class DagOrchestrator(metaclass=SingletonMeta):
    """Main DAG structure containing nodes and edges."""

    @dataclass(kw_only=True)
    class DagNode:
        """Represents a node in the DAG with runtime references."""

        node_reference: BaseNode
        thread_reference: Future | None = field(default=None)

    def __init__(self) -> None:
        self.network: nx.DiGraph = nx.DiGraph()




