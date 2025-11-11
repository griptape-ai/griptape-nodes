from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class LibrarySchemaValidationProblem(LibraryProblem):
    """Problem indicating a library schema validation error.

    This is stackable - multiple validation errors can occur when validating a library schema.
    """

    location: str
    error_type: str
    message: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[LibrarySchemaValidationProblem]) -> str:
        """Display library schema validation problems.

        Can handle multiple validation errors - they will be listed out.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"Error in section '{problem.location}': {problem.error_type}, {problem.message}"

        # Multiple validation errors - list them
        error_lines = []
        for i, problem in enumerate(instances, 1):
            error_lines.append(f"  {i}. Error in section '{problem.location}': {problem.error_type}, {problem.message}")

        header = f"Encountered {len(instances)} schema validation errors:"
        return header + "\n" + "\n".join(error_lines)
