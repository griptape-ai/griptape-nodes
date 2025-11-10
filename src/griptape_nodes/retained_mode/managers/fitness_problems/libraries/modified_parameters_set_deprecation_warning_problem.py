from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class ModifiedParametersSetDeprecationWarningProblem(LibraryProblem):
    """Problem warning that a library will be incompatible in the next version due to modified_parameters_set removal.

    This is stackable - multiple libraries can have this warning.
    This severity is FLAWED - the library can be loaded but has warnings.
    """

    library_engine_version: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[ModifiedParametersSetDeprecationWarningProblem]) -> str:
        """Display modified_parameters_set deprecation warnings.

        Can handle multiple instances - they will be listed out sorted by library_engine_version.
        """
        if len(instances) == 1:
            version = instances[0].library_engine_version
            return (
                f"WARNING: The 'modified_parameters_set' parameter will be removed in Griptape Nodes 0.39 from BaseNode methods: 'after_incoming_connection', 'after_outgoing_connection', 'after_incoming_connection_removed', 'after_outgoing_connection_removed', 'before_value_set', and 'after_value_set'. "
                f"This library (built for engine version {version}) must be updated before the 0.39 release. "
                "If this library overrides any of these methods, it will fail to load in 0.39. If not, no action is necessary. Please contact the library author to confirm whether this library is impacted."
            )

        # Multiple libraries with this warning - list them sorted by version
        sorted_instances = sorted(instances, key=lambda p: p.library_engine_version)
        error_lines = []
        for i, problem in enumerate(sorted_instances, 1):
            error_lines.append(
                f"  {i}. Library built for engine version {problem.library_engine_version} may be impacted by upcoming modified_parameters_set removal"
            )

        header = f"Encountered {len(instances)} libraries with modified_parameters_set deprecation warnings:"
        return header + "\n" + "\n".join(error_lines)
