from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class EngineVersionErrorProblem(LibraryProblem):
    """Problem indicating the engine version could not be retrieved for sandbox library generation."""

    @classmethod
    def collate_problems_for_display(cls, instances: list[EngineVersionErrorProblem]) -> str:
        """Display engine version error problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "EngineVersionErrorProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one EngineVersionErrorProblem.",
                len(instances),
            )

        return "Could not get engine version for sandbox library generation."
