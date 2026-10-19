"""What one open workflow is in the middle of loading."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


class WorkflowLoading:
    """Whether a workflow is being loaded, and which referenced workflow it is importing, if any.

    Per workflow, so two tabs loading at once don't silence each other's edits or tag each other's
    flows as imported.
    """

    def __init__(self) -> None:
        self._referenced_workflow_names: list[str] = []
        self._altered_squelch_depth = 0

    @contextmanager
    def squelch_altered(self) -> Iterator[None]:
        """Report requests handled in the block as leaving the workflow unaltered.

        Loading a workflow alters it request by request, and none of that should mark it unsaved.
        """
        self._altered_squelch_depth += 1
        try:
            yield
        finally:
            self._altered_squelch_depth -= 1

    def is_squelching_altered(self) -> bool:
        return self._altered_squelch_depth > 0

    @contextmanager
    def importing_referenced_workflow(self, workflow_name: str) -> Iterator[None]:
        """Tag the flows created in the block as imported from `workflow_name`."""
        self._referenced_workflow_names.append(workflow_name)
        try:
            yield
        finally:
            self._referenced_workflow_names.pop()

    def referenced_workflow_being_imported(self) -> str | None:
        """The referenced workflow the innermost import is running, or None outside one."""
        if not self._referenced_workflow_names:
            return None
        return self._referenced_workflow_names[-1]
