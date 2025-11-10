from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem


@dataclass
class DeprecatedNodeInWorkflowProblem(WorkflowProblem):
    """Problem indicating a workflow uses a deprecated node.

    This is stackable - workflows can use multiple deprecated nodes.
    """

    node_display_name: str
    node_type: str
    library_name: str
    current_library_version: str
    workflow_library_version: str | None
    removal_version: str | None
    deprecation_message: str | None

    @classmethod
    def collate_problems_for_display(cls, instances: list[DeprecatedNodeInWorkflowProblem]) -> str:
        """Display deprecated node in workflow problems.

        Groups by library, then by deprecation message within each library.
        """
        if len(instances) == 1:
            problem = instances[0]
            removal_info = (
                f"was removed in version {problem.removal_version}"
                if problem.removal_version
                else "may be removed in future versions"
            )
            message = f"This workflow uses node '{problem.node_display_name}' (class: {problem.node_type}) from library '{problem.library_name}', which is deprecated and {removal_info}. You are currently using library version: {problem.current_library_version}"
            if problem.workflow_library_version:
                message += f", and the workflow was saved with library version: {problem.workflow_library_version}"
            if problem.deprecation_message:
                message += f". The library author provided the following message for this deprecation: {problem.deprecation_message}"
            else:
                message += ". The library author did not provide a message explaining the deprecation. Contact the library author for details on how to remedy this."
            return message

        # Group by library
        by_library = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem)

        # Sort libraries alphabetically
        sorted_libraries = sorted(by_library.keys())

        output_lines = []
        output_lines.append(f"This workflow uses {len(instances)} deprecated nodes:")

        for library_name in sorted_libraries:
            nodes = by_library[library_name]
            output_lines.append(f"  From library '{library_name}':")

            # Group nodes within this library by deprecation_message
            by_message = defaultdict(list)
            for node in nodes:
                message_key = node.deprecation_message if node.deprecation_message else ""
                by_message[message_key].append(node)

            # Sort messages alphabetically (empty string first)
            sorted_messages = sorted(by_message.keys(), key=lambda m: (m != "", m))

            for message in sorted_messages:
                message_nodes = by_message[message]
                # Sort nodes by display_name within each message group
                message_nodes.sort(key=lambda p: p.node_display_name)

                if message:
                    output_lines.append(f"    {message}:")
                    output_lines.extend(f"      - {node.node_display_name}" for node in message_nodes)
                else:
                    # No deprecation message provided
                    output_lines.extend(
                        f"    - {node.node_display_name} (no deprecation message provided)" for node in message_nodes
                    )

        return "\n".join(output_lines)
