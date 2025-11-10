from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem


@dataclass
class NodeTypeNotFoundProblem(WorkflowProblem):
    """Problem indicating a workflow uses a node type that doesn't exist in current library version.

    This is stackable - workflows can reference multiple missing node types.
    """

    node_type: str
    library_name: str
    current_library_version: str
    workflow_library_version: str | None

    @classmethod
    def collate_problems_for_display(cls, instances: list[NodeTypeNotFoundProblem]) -> str:
        """Display node type not found problems.

        Groups by library_name, then sorts by node_type within each library.
        """
        if len(instances) == 1:
            problem = instances[0]
            message = f"This workflow uses node type '{problem.node_type}' from library '{problem.library_name}', but this node type is not found in the current library version {problem.current_library_version}"
            if problem.workflow_library_version:
                message += f". The workflow was saved with library version {problem.workflow_library_version}"
            message += ". This node may have been removed or renamed. Contact the library author for more details."
            return message

        # Group by library_name
        from collections import defaultdict

        by_library = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem)

        # Sort libraries alphabetically
        sorted_libraries = sorted(by_library.keys())

        output_lines = []
        output_lines.append(f"This workflow uses {len(instances)} node types that were not found:")

        for library_name in sorted_libraries:
            nodes = by_library[library_name]
            # Sort nodes by node_type within each library
            nodes.sort(key=lambda p: p.node_type)

            output_lines.append(f"  From library '{library_name}':")
            output_lines.extend(f"    - {node.node_type}" for node in nodes)

        return "\n".join(output_lines)
