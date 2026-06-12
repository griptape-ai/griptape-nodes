from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class UnresolvedModelProviderUsageReferenceProblem(LibraryProblem):
    """A node's `ModelProviderUsageNodeProperty.provider_ids` entry doesn't resolve.

    The catalog doesn't declare a provider with that id. The engine can't
    enumerate the offerings the node intended.

    Stackable.
    """

    library_name: str
    node_name: str
    provider_id: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[UnresolvedModelProviderUsageReferenceProblem]) -> str:
        if len(instances) == 1:
            problem = instances[0]
            return (
                f"Node '{problem.node_name}' in library '{problem.library_name}' references model provider "
                f"'{problem.provider_id}', which is not declared in the library's "
                f"ModelCatalogLibraryProperty."
            )

        by_library: dict[str, list[UnresolvedModelProviderUsageReferenceProblem]] = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem)

        output_lines = [f"Encountered {len(instances)} unresolved model provider references:"]
        for library_name in sorted(by_library.keys()):
            output_lines.append(f"  Library '{library_name}':")
            for problem in sorted(by_library[library_name], key=lambda p: (p.node_name, p.provider_id)):
                output_lines.append(  # noqa: PERF401  -- explicit loop is clearer than list.extend
                    f"    - node '{problem.node_name}' references missing provider '{problem.provider_id}'"
                )
        return "\n".join(output_lines)
