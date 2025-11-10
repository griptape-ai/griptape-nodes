from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem


@dataclass
class LibraryNotRegisteredProblem(WorkflowProblem):
    """Problem indicating a required library was not successfully registered.

    This is stackable - multiple libraries can fail to register.
    """

    library_name: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[LibraryNotRegisteredProblem]) -> str:
        """Display library not registered problems.

        Sorts by library_name and lists all affected libraries.
        """
        if len(instances) == 1:
            problem = instances[0]
            return f"Library '{problem.library_name}' was not successfully registered. It may have other problems that prevented it from loading."

        # Sort by library_name
        sorted_instances = sorted(instances, key=lambda p: p.library_name)

        output_lines = []
        output_lines.append(f"Encountered {len(instances)} unregistered libraries:")
        for i, problem in enumerate(sorted_instances, 1):
            output_lines.append(f"  {i}. {problem.library_name}")

        return "\n".join(output_lines)
