from abc import ABC, abstractmethod
from typing import Self


class LibraryProblem(ABC):
    """Base class for all library fitness problems."""

    @classmethod
    @abstractmethod
    def collate_problems_for_display(cls, instances: list[Self]) -> str:
        """Display one or more instances of this problem type.

        Handles both single and multiple instances with appropriate formatting.

        Args:
            instances: List of problem instances of this type to display.

        Returns:
            Formatted string describing the problem(s).
        """
