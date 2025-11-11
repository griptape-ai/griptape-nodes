from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class CreateConfigCategoryProblem(LibraryProblem):
    """Problem indicating a config category failed to be created."""

    category_name: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[CreateConfigCategoryProblem]) -> str:
        """Display config category creation problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "CreateConfigCategoryProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one CreateConfigCategoryProblem.",
                len(instances),
            )

        # Use the first instance's category name
        category = instances[0].category_name
        return f"Failed to create new config category '{category}'."
