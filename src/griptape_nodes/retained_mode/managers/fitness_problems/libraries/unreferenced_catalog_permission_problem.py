from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class UnreferencedCatalogPermissionProblem(LibraryProblem):
    """A library declared a permission name that nothing in the library references.

    This is a hygiene warning, not a load failure. Authors legitimately declare
    permissions in anticipation of nodes that reference them, so an unreferenced
    declaration is surfaced but does not block the library from loading.

    Stackable.
    """

    library_name: str
    permission_name: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[UnreferencedCatalogPermissionProblem]) -> str:
        if len(instances) == 1:
            problem = instances[0]
            return (
                f"Library '{problem.library_name}' declared permission "
                f"'{problem.permission_name}' in its catalog, but nothing in the library "
                f"references it."
            )

        by_library: dict[str, list[str]] = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem.permission_name)

        output_lines = [f"Encountered {len(instances)} unreferenced declared permissions:"]
        for library_name in sorted(by_library.keys()):
            names = ", ".join(f"'{n}'" for n in sorted(by_library[library_name]))
            output_lines.append(f"  Library '{library_name}' declared but unreferenced: {names}")
        return "\n".join(output_lines)
