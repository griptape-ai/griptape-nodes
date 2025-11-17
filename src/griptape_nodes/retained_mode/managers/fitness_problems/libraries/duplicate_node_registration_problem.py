from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class DuplicateNodeRegistrationProblem(LibraryProblem):
    """Problem indicating a node class was already registered.

    This is stackable - multiple duplicate registrations can occur.
    """

    class_name: str
    library_name: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[DuplicateNodeRegistrationProblem]) -> str:
        """Display duplicate node registration problems.

        Can handle multiple duplicates - they will be listed out sorted by class_name.
        """
        if len(instances) == 1:
            problem = instances[0]
            return (
                f"Attempted to register node class '{problem.class_name}' from library '{problem.library_name}', "
                f"but a node with that name from that library was already registered. "
                "Check to ensure you aren't re-adding the same libraries multiple times."
            )

        # Multiple duplicate registrations - list them sorted by class_name
        sorted_instances = sorted(instances, key=lambda p: p.class_name)
        error_lines = []
        for i, problem in enumerate(sorted_instances, 1):
            error_lines.append(
                f"  {i}. Node '{problem.class_name}' from library '{problem.library_name}' already registered"
            )

        header = f"Encountered {len(instances)} duplicate node registrations:"
        return header + "\n" + "\n".join(error_lines)
