from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem


@dataclass
class LibraryVersionBelowRequiredProblem(WorkflowProblem):
    """Problem indicating a library version is below the required version.

    This is stackable - multiple libraries can have versions below requirements.
    """

    library_name: str
    current_version: str
    required_version: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[LibraryVersionBelowRequiredProblem]) -> str:
        """Display library version below required problems.

        Sorts by library_name and lists all affected libraries.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"'{problem.library_name}' v{problem.current_version} below required v{problem.required_version}. Update library to match workflow requirements."

        # Sort by library_name
        sorted_instances = sorted(instances, key=lambda p: p.library_name)

        output_lines = []
        output_lines.append(
            f"{len(instances)} libraries below required versions. Update libraries to match workflow requirements:"
        )
        for i, problem in enumerate(sorted_instances, 1):
            output_lines.append(
                f"  {i}. {problem.library_name}: current v{problem.current_version}, required v{problem.required_version}"
            )

        return "\n".join(output_lines)
