from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class UnrecognizedMarkerDiscriminatorProblem(LibraryProblem):
    """A `marker_mapping` key is not one of the engine's recognized marker discriminators.

    The engine exposes a fixed set of marker-property discriminators
    (see permission_builtins.RECOGNIZED_MARKER_DISCRIMINATORS). A library can override
    mapping targets for those keys but cannot introduce new keys.

    Stackable.
    """

    library_name: str
    marker_key: str
    recognized_markers: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def collate_problems_for_display(cls, instances: list[UnrecognizedMarkerDiscriminatorProblem]) -> str:
        if len(instances) == 1:
            problem = instances[0]
            recognized = ", ".join(f"'{m}'" for m in sorted(problem.recognized_markers))
            return (
                f"Library '{problem.library_name}' specified marker_mapping key "
                f"'{problem.marker_key}', which is not a recognized marker discriminator. "
                f"Recognized markers: {recognized}."
            )

        by_library: dict[str, list[str]] = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem.marker_key)

        output_lines = [f"Encountered {len(instances)} unrecognized marker discriminators:"]
        for library_name in sorted(by_library.keys()):
            keys = ", ".join(f"'{k}'" for k in sorted(by_library[library_name]))
            output_lines.append(f"  Library '{library_name}' used unrecognized keys: {keys}")
        return "\n".join(output_lines)
