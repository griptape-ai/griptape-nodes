from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem


@dataclass
class InvalidLibraryVersionStringProblem(WorkflowProblem):
    """Problem indicating a registered library has an invalid version string.

    This is stackable - multiple libraries can have invalid version strings.
    """

    library_name: str
    version_string: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[InvalidLibraryVersionStringProblem]) -> str:
        """Display invalid library version string problems.

        Sorts by library_name and lists all affected libraries.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"'{problem.library_name}' has invalid version string '{problem.version_string}'. Must be major.minor.patch format."

        # Sort by library_name
        sorted_instances = sorted(instances, key=lambda p: p.library_name)

        output_lines = []
        output_lines.append(
            f"{len(instances)} libraries with invalid version strings (must be major.minor.patch format):"
        )
        for i, problem in enumerate(sorted_instances, 1):
            output_lines.append(f"  {i}. {problem.library_name}: '{problem.version_string}'")

        return "\n".join(output_lines)
