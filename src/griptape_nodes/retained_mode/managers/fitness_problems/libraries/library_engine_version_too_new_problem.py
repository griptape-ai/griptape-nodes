from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class LibraryEngineVersionTooNewProblem(LibraryProblem):
    """Problem indicating a library requires a newer engine version than currently running.

    This occurs when a library's engine_version metadata is greater than the current
    engine version, meaning the library was built for a newer engine and may use
    features that don't exist yet.
    """

    library_engine_version: str
    current_engine_version: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[LibraryEngineVersionTooNewProblem]) -> str:
        """Display engine version incompatibility problems.

        Can handle multiple instances - they will be listed out sorted by library_engine_version.
        """
        if len(instances) == 1:
            p = instances[0]
            return (
                f"This library requires engine version {p.library_engine_version} but the current "
                f"engine version is {p.current_engine_version}. Please update your engine to use this library."
            )

        # Multiple libraries with this issue - list them sorted by required version
        sorted_instances = sorted(instances, key=lambda p: p.library_engine_version)
        error_lines = []
        for i, problem in enumerate(sorted_instances, 1):
            error_lines.append(
                f"  {i}. Requires engine version {problem.library_engine_version} (current: {problem.current_engine_version})"
            )

        header = f"Encountered {len(instances)} libraries requiring newer engine versions:"
        return header + "\n" + "\n".join(error_lines)
