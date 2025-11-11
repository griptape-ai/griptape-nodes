from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class UiOptionsFieldModifiedWarningProblem(LibraryProblem):
    """Problem warning that a library may not function properly due to ui_options field modification.

    This is stackable - multiple libraries can have this warning.
    This severity is FLAWED - the library can be loaded but has warnings.
    """

    @classmethod
    def collate_problems_for_display(cls, instances: list[UiOptionsFieldModifiedWarningProblem]) -> str:
        """Display ui_options field modification warnings.

        Can handle multiple instances.
        """
        if len(instances) > 1:
            logger.error(
                "UiOptionsFieldModifiedWarningProblem: Expected 1 instance but got %s. This warning should only appear once per library.",
                len(instances),
            )

        return (
            "WARNING: The 'ui_options' field has been modified in Griptape Nodes 0.38 on all BaseNodeElements."
            "In order to function properly, all nodes must update ui_options by setting its value to a new dictionary. Updating ui_options by accessing the private field _ui_options will no longer create UI updates in the editor."
            "If this library accesses the private _ui_options field, it will not update the editor properly. Please update to a newer version of this library or contact the library author immediately."
        )
