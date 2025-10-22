"""Validation infrastructure for project templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ProjectValidationStatus(StrEnum):
    """Status of project template validation.

    Mirrors WorkflowStatus pattern from workflow_manager.py.
    """

    GOOD = "GOOD"  # No errors detected
    FLAWED = "FLAWED"  # Some errors, but recoverable
    UNUSABLE = "UNUSABLE"  # Errors make template unusable
    MISSING = "MISSING"  # File not found


class ProjectValidationProblemSeverity(StrEnum):
    """Severity level of a validation problem."""

    ERROR = "error"
    WARNING = "warning"


class ProjectOverrideCategory(StrEnum):
    """Category of template override during merge."""

    SITUATION = "situation"
    DIRECTORY = "directory"
    ENVIRONMENT = "environment"
    METADATA = "metadata"


class ProjectOverrideAction(StrEnum):
    """Action taken during template merge."""

    MODIFIED = "modified"  # Existed in base, changed in overlay
    ADDED = "added"  # New in overlay, not in base


@dataclass
class ProjectValidationProblem:
    """Single validation problem with context."""

    line_number: int | None
    field_path: str  # e.g., "situations.copy_external_file.schema"
    message: str
    severity: ProjectValidationProblemSeverity


@dataclass
class ProjectValidationInfo:
    """Validation result for a project template.

    Shared across construction chain - problems are accumulated as
    the template is built from YAML.
    """

    status: ProjectValidationStatus
    problems: list[ProjectValidationProblem] = field(default_factory=list)

    def add_error(self, field_path: str, message: str, line_number: int | None = None) -> None:
        """Add an error to the problems list.

        Automatically downgrades status to UNUSABLE unless already MISSING.
        Early returns if status is MISSING.
        """
        if self.status == ProjectValidationStatus.MISSING:
            return

        self.problems.append(
            ProjectValidationProblem(
                line_number=line_number,
                field_path=field_path,
                message=message,
                severity=ProjectValidationProblemSeverity.ERROR,
            )
        )
        self.status = ProjectValidationStatus.UNUSABLE

    def add_warning(self, field_path: str, message: str, line_number: int | None = None) -> None:
        """Add a warning to the problems list.

        Automatically downgrades status from GOOD to FLAWED if current status is GOOD.
        Does not change status if already FLAWED or UNUSABLE.
        Early returns if status is MISSING.
        """
        if self.status == ProjectValidationStatus.MISSING:
            return

        self.problems.append(
            ProjectValidationProblem(
                line_number=line_number,
                field_path=field_path,
                message=message,
                severity=ProjectValidationProblemSeverity.WARNING,
            )
        )

        if self.status == ProjectValidationStatus.GOOD:
            self.status = ProjectValidationStatus.FLAWED
