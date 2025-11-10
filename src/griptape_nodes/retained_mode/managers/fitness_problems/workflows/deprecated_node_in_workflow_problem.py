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
                f"removed in v{problem.removal_version}" if problem.removal_version else "may be removed in future"
            )
            message = (
                f"Uses deprecated node '{problem.node_display_name}' from '{problem.library_name}' ({removal_info})"
            )
            if problem.deprecation_message:
                message += f". {problem.deprecation_message}"
            else:
                message += ". No remediation steps provided by library author."
            return message

        # Group by library
        by_library = defaultdict(list)
        for problem in instances:
            by_library[problem.library_name].append(problem)

        # Sort libraries alphabetically
        sorted_libraries = sorted(by_library.keys())

        output_lines = []
        output_lines.append(f"Uses {len(instances)} deprecated nodes:")

        for library_name in sorted_libraries:
            nodes = by_library[library_name]
            output_lines.append(f"  From '{library_name}':")

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
                    # No remediation steps provided
                    output_lines.extend(
                        f"    - {node.node_display_name} (no remediation steps provided by library author)"
                        for node in message_nodes
                    )

        return "\n".join(output_lines)
