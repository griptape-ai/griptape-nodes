from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class NodeModuleImportProblem(LibraryProblem):
    """Problem indicating a node module could not be imported.

    This is stackable - multiple node modules can fail to import.
    """

    class_name: str
    file_path: str
    error_message: str
    root_cause: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[NodeModuleImportProblem]) -> str:
        """Display node module import problems.

        Groups by root_cause and lists affected nodes under each cause.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"Failed to import module for node '{problem.class_name}': {problem.root_cause}"

        # Group by root_cause
        by_cause = defaultdict(list)
        for problem in instances:
            by_cause[problem.root_cause].append(problem)

        # Sort root causes alphabetically
        sorted_causes = sorted(by_cause.keys())

        output_lines = []
        output_lines.append(f"Encountered {len(instances)} node module import failures:")

        for cause in sorted_causes:
            nodes = by_cause[cause]
            # Sort nodes by class_name within each cause group
            nodes.sort(key=lambda p: p.class_name)

            output_lines.append(f"  {cause}:")
            output_lines.extend(f"    - {node.class_name}" for node in nodes)

        return "\n".join(output_lines)
