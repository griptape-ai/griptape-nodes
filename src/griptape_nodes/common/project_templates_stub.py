"""Stub implementations for project template types.

These are temporary stubs to enable ProjectManager development while the project
template system PR is under review. Once the PR merges, these will be replaced
with the actual implementations from griptape_nodes.common.project_templates.

TODO: Remove this file and replace imports when project template PR merges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class ProjectValidationStatus(StrEnum):
    """Status of project template validation."""

    GOOD = "GOOD"  # No errors detected
    FLAWED = "FLAWED"  # Some errors, but recoverable
    UNUSABLE = "UNUSABLE"  # Errors make template unusable
    MISSING = "MISSING"  # File not found


class ProjectValidationProblemSeverity(StrEnum):
    """Severity level of a validation problem."""

    ERROR = "error"
    WARNING = "warning"


@dataclass
class ProjectValidationProblem:
    """Single validation problem with context."""

    line_number: int | None
    field_path: str
    message: str
    severity: ProjectValidationProblemSeverity


@dataclass
class ProjectValidationInfo:
    """Validation result for a project template."""

    status: ProjectValidationStatus
    problems: list[ProjectValidationProblem] = field(default_factory=list)

    def is_usable(self) -> bool:
        """Check if template can be used (GOOD or FLAWED status)."""
        return self.status in (ProjectValidationStatus.GOOD, ProjectValidationStatus.FLAWED)

    def add_error(self, field_path: str, message: str, line_number: int | None = None) -> None:
        """Add an error to the problems list."""
        self.problems.append(
            ProjectValidationProblem(
                line_number=line_number,
                field_path=field_path,
                message=message,
                severity=ProjectValidationProblemSeverity.ERROR,
            )
        )
        if self.status != ProjectValidationStatus.MISSING:
            self.status = ProjectValidationStatus.UNUSABLE


class SituationFilePolicy(StrEnum):
    """File collision policy."""

    CREATE_NEW = "create_new"
    OVERWRITE = "overwrite"
    FAIL = "fail"
    PROMPT = "prompt"


@dataclass
class SituationPolicy:
    """Policy for handling file operations in a situation."""

    on_collision: SituationFilePolicy
    create_dirs: bool


@dataclass
class SituationTemplate:
    """Template defining how files are saved in a specific situation."""

    name: str
    situation_template_schema_version: str
    schema: str  # Path schema with macro syntax
    policy: SituationPolicy
    fallback: str | None = None
    description: str | None = None


@dataclass
class DirectoryDefinition:
    """Definition of a logical project directory."""

    name: str
    path_schema: str  # Path schema with macro syntax


@dataclass
class ProjectTemplate:
    """Complete project template loaded from project.yml."""

    project_template_schema_version: str
    name: str
    situations: dict[str, SituationTemplate]
    directories: dict[str, DirectoryDefinition]
    environment: dict[str, str]
    description: str | None = None

    def get_situation(self, situation_name: str) -> SituationTemplate | None:
        """Get a situation by name, returns None if not found."""
        return self.situations.get(situation_name)

    def get_directory(self, directory_name: str) -> DirectoryDefinition | None:
        """Get a directory definition by logical name."""
        return self.directories.get(directory_name)


# System default template path
DEFAULT_PROJECT_YAML_PATH = Path(__file__).parent / "project_templates" / "defaults" / "project_template.yml"
