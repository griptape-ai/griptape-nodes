from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class DuplicateWidgetRegistrationProblem(LibraryProblem):
    """Problem indicating a widget name was already registered.

    This is stackable - multiple duplicate registrations can occur.
    """

    widget_name: str
    library_name: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[DuplicateWidgetRegistrationProblem]) -> str:
        """Display duplicate widget registration problems.

        Can handle multiple duplicates - they will be listed out sorted by widget_name.
        """
        if len(instances) == 1:
            problem = instances[0]
            return (
                f"Attempted to register widget '{problem.widget_name}' from library '{problem.library_name}', "
                f"but a widget with that name from that library was already registered. "
                "Check to ensure you aren't re-adding the same libraries multiple times."
            )

        # Multiple duplicate registrations - list them sorted by widget_name
        sorted_instances = sorted(instances, key=lambda p: p.widget_name)
        error_lines = []
        for i, problem in enumerate(sorted_instances, 1):
            error_lines.append(
                f"  {i}. Widget '{problem.widget_name}' from library '{problem.library_name}' already registered"
            )

        header = f"Encountered {len(instances)} duplicate widget registrations:"
        return header + "\n" + "\n".join(error_lines)
