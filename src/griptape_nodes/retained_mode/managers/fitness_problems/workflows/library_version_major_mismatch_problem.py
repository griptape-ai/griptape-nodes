from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem


@dataclass
class LibraryVersionMajorMismatchProblem(WorkflowProblem):
    """Problem indicating a library has a major version mismatch from what workflow expects.

    This is stackable - multiple libraries can have major version mismatches.
    """

    library_name: str
    workflow_version: str
    current_version: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[LibraryVersionMajorMismatchProblem]) -> str:
        """Display library version major mismatch problems.

        Sorts by library_name and lists all affected libraries.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"Saved with '{problem.library_name}' v{problem.workflow_version}. You have v{problem.current_version}. Major version changes may include breaking changes. Re-save workflow (likely requires manual adjustments) to update to latest."

        # Sort by library_name
        sorted_instances = sorted(instances, key=lambda p: p.library_name)

        output_lines = []
        output_lines.append(
            f"Uses {len(instances)} libraries with major version mismatches (may include breaking changes). Re-save workflow (likely requires manual adjustments) to update to latest:"
        )
        for i, problem in enumerate(sorted_instances, 1):
            output_lines.append(
                f"  {i}. {problem.library_name}: saved with v{problem.workflow_version}, current v{problem.current_version}"
            )

        return "\n".join(output_lines)
