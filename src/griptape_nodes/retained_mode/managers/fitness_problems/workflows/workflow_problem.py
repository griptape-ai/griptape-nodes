from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Self


class WorkflowProblem(ABC):
    """Base class for all workflow fitness problems."""

    @classmethod
    @abstractmethod
    def collate_problems_for_display(cls, instances: list[Self]) -> str:
        """Collate one or more instances of this problem type for display.

        Args:
            instances: List of problem instances of this type

        Returns:
            A formatted string suitable for displaying to the user
        """
