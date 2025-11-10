from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class SandboxDirectoryMissingProblem(LibraryProblem):
    """Problem indicating the sandbox directory does not exist."""

    @classmethod
    def collate_problems_for_display(cls, instances: list[SandboxDirectoryMissingProblem]) -> str:
        """Display sandbox directory missing problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "SandboxDirectoryMissingProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one SandboxDirectoryMissingProblem.",
                len(instances),
            )

        return "Sandbox directory does not exist. If you wish to create a Sandbox directory to develop custom nodes: in the Griptape Nodes editor, go to Settings -> Libraries and navigate to the Sandbox Settings."
