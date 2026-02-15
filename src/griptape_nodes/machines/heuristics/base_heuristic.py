"""Base class for node priority heuristics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.machines.dag_builder import DagNode
    from griptape_nodes.machines.parallel_resolution import ParallelResolutionContext


class NodeHeuristic(ABC):
    """Base class for node priority heuristics."""

    def __init__(self, context: ParallelResolutionContext, weight: float = 1, max_value: float = 100.0) -> None:
        self._context = context
        # The weight of this specific heuristic. Higher weight means higher priority, assuming the maximum values are the same (otherwise weight will have less of an effect)
        self._weight = weight
        # This is the value we use to get the maximum value that we want to allow to be set for a heuristic.
        self.max_value = max_value

    @property
    def weight(self) -> float:
        return self._weight

    @weight.setter
    def weight(self, value: float) -> None:
        self._weight = value

    @abstractmethod
    def calculate_priority(self, dag_node: DagNode, **kwargs) -> float:
        pass

    @abstractmethod
    def calculate_priorities_batch(self, dag_nodes: list[DagNode], **kwargs) -> dict[str, float]:
        """Calculate priorities for multiple nodes at once.

        Default implementation calls calculate_priority for each node.
        Subclasses can override for better performance.

        Args:
            dag_nodes: List of nodes to calculate priorities for
            **kwargs: Additional arguments passed to calculate_priority

        Returns:
            Dictionary mapping node names to priority scores
        """
