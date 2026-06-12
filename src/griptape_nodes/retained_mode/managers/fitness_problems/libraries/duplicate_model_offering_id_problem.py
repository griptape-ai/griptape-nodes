from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class DuplicateModelOfferingIdProblem(LibraryProblem):
    """The same offering id appears in two different parents within a library's catalog.

    Pydantic enforces sibling-uniqueness within a single ``offerings`` dict, so
    this only fires when the *same* id is used under different providers or
    families (e.g. once under ``anthropic.claude_4.offerings`` and again under
    ``kling.offerings``). Cross-parent duplicates break admin policies and
    runtime resolution: a node referencing the id can't pick which of the
    two parents it meant.

    Stackable.
    """

    library_name: str
    offering_id: str
    # Parent paths where this id appeared (e.g. "anthropic/claude_4", "kling").
    parent_paths: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def collate_problems_for_display(cls, instances: list[DuplicateModelOfferingIdProblem]) -> str:
        if len(instances) == 1:
            problem = instances[0]
            paths = ", ".join(f"'{p}'" for p in problem.parent_paths)
            return (
                f"Library '{problem.library_name}' declares offering id "
                f"'{problem.offering_id}' under multiple parents: {paths}. "
                f"Offering ids must be unique across the library."
            )

        by_library: dict[str, list[DuplicateModelOfferingIdProblem]] = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem)

        output_lines = [f"Encountered {len(instances)} duplicate model offering ids:"]
        for library_name in sorted(by_library.keys()):
            output_lines.append(f"  Library '{library_name}':")
            for problem in sorted(by_library[library_name], key=lambda p: p.offering_id):
                paths = ", ".join(f"'{p}'" for p in problem.parent_paths)
                output_lines.append(f"    - id '{problem.offering_id}' appears under: {paths}")
        return "\n".join(output_lines)
