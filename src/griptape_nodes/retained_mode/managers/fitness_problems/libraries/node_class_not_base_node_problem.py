from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class NodeClassNotBaseNodeProblem(LibraryProblem):
    """Problem indicating a node class doesn't inherit from BaseNode.

    This is stackable - multiple node classes can have incorrect inheritance.
    """

    class_name: str
    file_path: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[NodeClassNotBaseNodeProblem]) -> str:
        """Display node class inheritance problems.

        Can handle multiple non-BaseNode classes - they will be listed out sorted by class_name.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"Class '{problem.class_name}' from {problem.file_path} must inherit from BaseNode"

        # Multiple inheritance issues - list them sorted by class_name
        sorted_instances = sorted(instances, key=lambda p: p.class_name)
        error_lines = []
        for i, problem in enumerate(sorted_instances, 1):
            error_lines.append(
                f"  {i}. Class '{problem.class_name}' from {problem.file_path} must inherit from BaseNode"
            )

        header = f"Encountered {len(instances)} node classes that don't inherit from BaseNode:"
        return header + "\n" + "\n".join(error_lines)
