from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class BuiltinPermissionShadowedProblem(LibraryProblem):
    """A library's permission catalog redeclares a permission name owned by the engine.

    Built-in permission names (see permission_builtins.BUILTIN_PERMISSIONS) are owned
    by the engine and cannot be shadowed by a library's own declaration. Libraries
    that need distinct behavior should pick a different name.

    Stackable: a library can shadow multiple built-ins in one load attempt.
    """

    library_name: str
    permission_name: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[BuiltinPermissionShadowedProblem]) -> str:
        if len(instances) == 1:
            problem = instances[0]
            return (
                f"Library '{problem.library_name}' redeclared built-in permission "
                f"'{problem.permission_name}'. Built-in permissions cannot be shadowed."
            )

        by_library: dict[str, list[str]] = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem.permission_name)

        output_lines = [f"Encountered {len(instances)} shadowed built-in permissions:"]
        for library_name in sorted(by_library.keys()):
            names = ", ".join(f"'{n}'" for n in sorted(by_library[library_name]))
            output_lines.append(f"  Library '{library_name}' redeclared: {names}")
        return "\n".join(output_lines)
