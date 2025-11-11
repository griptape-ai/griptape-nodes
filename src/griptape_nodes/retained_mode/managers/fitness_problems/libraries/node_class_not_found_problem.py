from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class NodeClassNotFoundProblem(LibraryProblem):
    """Problem indicating a node class was not found in its module.

    This is stackable - multiple node classes can be missing.
    """

    class_name: str
    file_path: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[NodeClassNotFoundProblem]) -> str:
        """Display node class not found problems.

        Can handle multiple missing classes - they will be listed out sorted by class_name.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"Class '{problem.class_name}' not found in module '{problem.file_path}'"

        # Multiple missing classes - list them sorted by class_name
        sorted_instances = sorted(instances, key=lambda p: p.class_name)
        error_lines = []
        for i, problem in enumerate(sorted_instances, 1):
            error_lines.append(f"  {i}. Class '{problem.class_name}' not found in '{problem.file_path}'")

        header = f"Encountered {len(instances)} node classes not found in their modules:"
        return header + "\n" + "\n".join(error_lines)
