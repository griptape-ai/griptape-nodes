from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem


@dataclass
class LibraryVersionLargeDifferenceProblem(WorkflowProblem):
    """Problem indicating a library has a large version difference from what workflow expects.

    This is stackable - multiple libraries can have large version differences.
    """

    library_name: str
    workflow_version: str
    current_version: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[LibraryVersionLargeDifferenceProblem]) -> str:
        """Display library version large difference problems.

        Sorts by library_name and lists all affected libraries.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"This workflow was built with library '{problem.library_name}' v{problem.workflow_version}, but you have v{problem.current_version}. This large version difference may cause compatibility issues. You can update the library to a compatible version or save this workflow to update it to your current library versions."

        # Sort by library_name
        sorted_instances = sorted(instances, key=lambda p: p.library_name)

        output_lines = []
        output_lines.append(
            f"Encountered {len(instances)} libraries with large version differences (may cause compatibility issues):"
        )
        for i, problem in enumerate(sorted_instances, 1):
            output_lines.append(
                f"  {i}. {problem.library_name}: workflow used v{problem.workflow_version}, current v{problem.current_version}"
            )

        return "\n".join(output_lines)
