from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


class PermissionReferenceSite(StrEnum):
    """Where in the library a permission name was referenced.

    Used to disambiguate the same error type across several declaration sites so
    display and diagnostics can describe the exact location.
    """

    LIBRARY_REQUIRED_PERMISSIONS = "library_required_permissions"
    NODE_REQUIRED_PERMISSIONS = "node_required_permissions"
    MARKER_MAPPING_TARGET = "marker_mapping_target"
    MODEL_ENTITLEMENT_REQUIRES_PERMISSION = "model_entitlement_requires_permission"


@dataclass
class UndeclaredPermissionReferenceProblem(LibraryProblem):
    """A permission name was referenced but is not declared in the effective catalog.

    The effective catalog is the union of the engine's built-in permissions and the
    library's own `PermissionCatalogLibraryProperty.permissions`. A reference that
    does not resolve against that union blocks library load.

    Stackable: a single library can carry multiple undeclared references.
    """

    library_name: str
    reference_site: PermissionReferenceSite
    permission_name: str
    # Populated when `reference_site` is NODE_REQUIRED_PERMISSIONS.
    node_name: str | None = None
    # Populated when `reference_site` is MARKER_MAPPING_TARGET.
    marker_key: str | None = None
    # Populated when `reference_site` is MODEL_ENTITLEMENT_REQUIRES_PERMISSION.
    entitlement_name: str | None = None

    @classmethod
    def collate_problems_for_display(cls, instances: list[UndeclaredPermissionReferenceProblem]) -> str:
        if len(instances) == 1:
            return cls._describe_one(instances[0])

        by_library: dict[str, list[UndeclaredPermissionReferenceProblem]] = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem)

        output_lines = [f"Encountered {len(instances)} undeclared permission references:"]
        for library_name in sorted(by_library.keys()):
            output_lines.append(f"  Library '{library_name}':")
            output_lines.extend(f"    - {cls._describe_site(problem)}" for problem in by_library[library_name])
        return "\n".join(output_lines)

    @classmethod
    def _describe_one(cls, problem: UndeclaredPermissionReferenceProblem) -> str:
        return (
            f"Library '{problem.library_name}' references permission "
            f"'{problem.permission_name}' at {cls._describe_site(problem)}, but that "
            f"permission is not declared in the library's permission catalog or by the "
            f"engine's built-in permissions."
        )

    @staticmethod
    def _describe_site(problem: UndeclaredPermissionReferenceProblem) -> str:
        match problem.reference_site:
            case PermissionReferenceSite.LIBRARY_REQUIRED_PERMISSIONS:
                return f"library-level required permission '{problem.permission_name}'"
            case PermissionReferenceSite.NODE_REQUIRED_PERMISSIONS:
                return f"node '{problem.node_name}' required permission '{problem.permission_name}'"
            case PermissionReferenceSite.MARKER_MAPPING_TARGET:
                return f"marker_mapping['{problem.marker_key}'] -> '{problem.permission_name}'"
            case PermissionReferenceSite.MODEL_ENTITLEMENT_REQUIRES_PERMISSION:
                return f"model entitlement '{problem.entitlement_name}' requires_permission '{problem.permission_name}'"
