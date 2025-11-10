from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class AfterLibraryCallbackProblem(LibraryProblem):
    """Problem indicating an error calling the after_library_nodes_loaded callback."""

    error_message: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[AfterLibraryCallbackProblem]) -> str:
        """Display after library callback problem.

        There should only be one instance per library since there's only one
        after_library_nodes_loaded callback per library.
        """
        if len(instances) > 1:
            logger.error(
                "AfterLibraryCallbackProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one AfterLibraryCallbackProblem.",
                len(instances),
            )

        # Use the first instance's error message
        error_msg = instances[0].error_message
        return f"Error calling after_library_nodes_loaded callback: {error_msg}"
