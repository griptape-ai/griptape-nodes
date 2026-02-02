from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class DuplicateComponentRegistrationProblem(LibraryProblem):
    """Problem indicating a component name was already registered.

    This is stackable - multiple duplicate registrations can occur.
    """

    component_name: str
    library_name: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[DuplicateComponentRegistrationProblem]) -> str:
        """Display duplicate component registration problems.

        Can handle multiple duplicates - they will be listed out sorted by component_name.
        """
        if len(instances) == 1:
            problem = instances[0]
            return (
                f"Attempted to register component '{problem.component_name}' from library '{problem.library_name}', "
                f"but a component with that name from that library was already registered. "
                "Check to ensure you aren't re-adding the same libraries multiple times."
            )

        # Multiple duplicate registrations - list them sorted by component_name
        sorted_instances = sorted(instances, key=lambda p: p.component_name)
        error_lines = []
        for i, problem in enumerate(sorted_instances, 1):
            error_lines.append(
                f"  {i}. Component '{problem.component_name}' from library '{problem.library_name}' already registered"
            )

        header = f"Encountered {len(instances)} duplicate component registrations:"
        return header + "\n" + "\n".join(error_lines)
