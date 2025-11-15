from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class UiOptionsFieldModifiedIncompatibleProblem(LibraryProblem):
    """Problem indicating a library is incompatible due to ui_options field modification.

    This is stackable - multiple libraries can have this issue.
    This severity is UNUSABLE - the library cannot be loaded.
    """

    library_engine_version: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[UiOptionsFieldModifiedIncompatibleProblem]) -> str:
        """Display ui_options field modification incompatibility problems.

        Can handle multiple instances - they will be listed out sorted by library_engine_version.
        """
        if len(instances) == 1:
            version = instances[0].library_engine_version
            return (
                f"This library (built for engine version {version}) is incompatible with Griptape Nodes 0.39+."
                "The 'ui_options' field has been modified on all Elements. In order to function properly, all nodes must update ui_options by setting its value to a new dictionary. Updating ui_options by accessing the private field _ui_options will no longer create UI updates in the editor."
                "If this library accesses the private _ui_options field, it will not update the editor properly. Please update to a newer version of this library or contact the library author immediately."
            )

        # Multiple libraries with this issue - list them sorted by version
        sorted_instances = sorted(instances, key=lambda p: p.library_engine_version)
        error_lines = []
        for i, problem in enumerate(sorted_instances, 1):
            error_lines.append(
                f"  {i}. Library built for engine version {problem.library_engine_version} is incompatible due to ui_options field modification"
            )

        header = f"Encountered {len(instances)} libraries incompatible due to ui_options field modification:"
        return header + "\n" + "\n".join(error_lines)
