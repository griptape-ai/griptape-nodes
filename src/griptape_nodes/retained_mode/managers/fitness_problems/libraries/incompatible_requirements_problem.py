from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class IncompatibleRequirementsProblem(LibraryProblem):
    """Problem indicating library requirements are not met by the current system."""

    requirements: dict[str, Any]
    system_capabilities: dict[str, Any]

    @classmethod
    def collate_problems_for_display(cls, instances: list[IncompatibleRequirementsProblem]) -> str:
        """Display incompatible requirements problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "IncompatibleRequirementsProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one IncompatibleRequirementsProblem.",
                len(instances),
            )

        # Use the first instance's details
        problem = instances[0]
        return f"Library requirements not met. Required: {problem.requirements}, System: {problem.system_capabilities}"
