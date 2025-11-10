from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem


@dataclass
class InvalidDependencyVersionStringProblem(WorkflowProblem):
    """Problem indicating workflow cited an invalid version string for a library dependency.

    This is stackable - multiple libraries can have invalid version strings.
    """

    library_name: str
    version_string: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[InvalidDependencyVersionStringProblem]) -> str:
        """Display invalid dependency version string problems.

        Sorts by library_name and lists all affected libraries.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"Workflow cited an invalid version string '{problem.version_string}' for library '{problem.library_name}'. Must be specified in major.minor.patch format."

        # Sort by library_name
        sorted_instances = sorted(instances, key=lambda p: p.library_name)

        output_lines = []
        output_lines.append(f"Encountered {len(instances)} invalid dependency version strings:")
        for i, problem in enumerate(sorted_instances, 1):
            output_lines.append(
                f"  {i}. Library '{problem.library_name}' has invalid version string '{problem.version_string}'"
            )

        return "\n".join(output_lines)
