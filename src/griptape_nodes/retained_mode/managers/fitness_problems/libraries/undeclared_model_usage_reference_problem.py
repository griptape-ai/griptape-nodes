from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class UndeclaredModelUsageReferenceProblem(LibraryProblem):
    """A `ModelUsageNodeProperty.name` does not resolve to a declared model entitlement.

    Nodes reference model entitlements by short name from the library's
    `ModelCatalogLibraryProperty.entitlements`. A reference that is not declared in
    the catalog cannot be resolved at runtime and blocks library load.

    Stackable.
    """

    library_name: str
    node_name: str
    entitlement_name: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[UndeclaredModelUsageReferenceProblem]) -> str:
        if len(instances) == 1:
            problem = instances[0]
            return (
                f"Node '{problem.node_name}' in library '{problem.library_name}' "
                f"references model entitlement '{problem.entitlement_name}', but that "
                f"entitlement is not declared in the library's ModelCatalogLibraryProperty."
            )

        by_library: dict[str, list[UndeclaredModelUsageReferenceProblem]] = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem)

        output_lines = [f"Encountered {len(instances)} undeclared model_usage references:"]
        for library_name in sorted(by_library.keys()):
            output_lines.append(f"  Library '{library_name}':")
            output_lines.extend(
                f"    - node '{problem.node_name}' references entitlement '{problem.entitlement_name}'"
                for problem in sorted(by_library[library_name], key=lambda p: (p.node_name, p.entitlement_name))
            )
        return "\n".join(output_lines)
