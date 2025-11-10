from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class ModifiedParametersSetRemovedProblem(LibraryProblem):
    """Problem indicating a library is incompatible due to modified_parameters_set removal.

    This is stackable - multiple libraries can have this issue.
    This severity is UNUSABLE - the library cannot be loaded.
    """

    library_engine_version: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[ModifiedParametersSetRemovedProblem]) -> str:
        """Display modified_parameters_set removal problems.

        Can handle multiple instances - they will be listed out sorted by library_engine_version.
        """
        if len(instances) == 1:
            version = instances[0].library_engine_version
            return (
                f"This library (built for engine version {version}) is incompatible with Griptape Nodes 0.39+. "
                "The 'modified_parameters_set' parameter has been removed from BaseNode methods: 'after_incoming_connection', 'after_outgoing_connection', 'after_incoming_connection_removed', 'after_outgoing_connection_removed', 'before_value_set', and 'after_value_set'. "
                "If this library overrides any of these methods, it will not load or function properly. Please update to a newer version of this library or contact the library author immediately."
            )

        # Multiple libraries with this issue - list them sorted by version
        sorted_instances = sorted(instances, key=lambda p: p.library_engine_version)
        error_lines = []
        for i, problem in enumerate(sorted_instances, 1):
            error_lines.append(
                f"  {i}. Library built for engine version {problem.library_engine_version} is incompatible due to modified_parameters_set removal"
            )

        header = f"Encountered {len(instances)} libraries incompatible due to modified_parameters_set removal:"
        return header + "\n" + "\n".join(error_lines)
