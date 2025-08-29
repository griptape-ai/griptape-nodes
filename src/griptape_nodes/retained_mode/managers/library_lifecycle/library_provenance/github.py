"""GitHub library provenance implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from xdg_base_dirs import xdg_data_home

from griptape_nodes.retained_mode.managers.library_lifecycle.data_models import (
    EvaluationResult,
    InspectionResult,
    InstallationResult,
    LibraryLoadedResult,
    LifecycleIssue,
)
from griptape_nodes.retained_mode.managers.library_lifecycle.library_provenance.base import LibraryProvenance
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.library_lifecycle.library_fsm import LibraryLifecycleContext


class LibraryPreferenceGitHub(BaseModel):
    """Serializable preference for a GitHub repository library."""

    repository_url: str = Field(description="GitHub repository URL")
    branch: str | None = Field(default=None, description="Branch or ref to use (defaults to main/master)")
    active: bool = Field(default=True, description="Whether this GitHub library is active")


@dataclass(frozen=True)
class LibraryProvenanceGitHub(LibraryProvenance):
    """Reference to a GitHub repository library."""

    repository_url: str
    ref: str | None = None

    def get_display_name(self) -> str:
        """Get a human-readable name for this provenance."""
        ref_part = f"@{self.ref}" if self.ref else ""
        return f"GitHub: {self.repository_url}{ref_part}"

    def inspect(self) -> InspectionResult:
        """Inspect this GitHub repository to extract schema and identify issues."""
        # TODO: Implement GitHub repository inspection (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # This should:
        # 1. Clone or fetch repository contents
        # 2. Look for library schema files
        # 3. Extract and validate library schema

        return InspectionResult(
            schema=None,
            issues=[
                LifecycleIssue(
                    message=f"GitHub inspection not yet implemented for {self.repository_url}",
                    severity=LibraryStatus.UNUSABLE,
                )
            ],
        )

    def evaluate(self, context: LibraryLifecycleContext) -> EvaluationResult:  # noqa: ARG002
        """Evaluate this GitHub repository for conflicts/issues."""
        issues = []
        issues.append(
            LifecycleIssue(
                message="GitHub evaluation not yet implemented",
                severity=LibraryStatus.UNUSABLE,
            )
        )
        return EvaluationResult(issues=issues)

    async def install(self, context: LibraryLifecycleContext) -> InstallationResult:  # noqa: ARG002
        """Install this GitHub repository library."""
        issues = []
        issues.append(
            LifecycleIssue(
                message="GitHub installation not yet implemented",
                severity=LibraryStatus.UNUSABLE,
            )
        )

        # TODO: Implement GitHub repository installation (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # This should:
        # 1. Clone repository to local directory
        # 2. Create virtual environment
        # 3. Install dependencies
        # 4. Install repository in development mode

        return InstallationResult(
            installation_path="",
            venv_path="",
            issues=issues,
        )

    def load_library(self, context: LibraryLifecycleContext) -> LibraryLoadedResult:  # noqa: ARG002
        """Load this GitHub repository library into the registry."""
        issues = []
        issues.append(
            LifecycleIssue(
                message="GitHub loading not yet implemented",
                severity=LibraryStatus.UNUSABLE,
            )
        )

        return LibraryLoadedResult(issues=issues)

    def _get_base_venv_directory(self) -> str:
        """Get the base directory for virtual environments."""
        return str(xdg_data_home() / "griptape_nodes" / "library_venvs")

    def _ensure_venv_directory_exists(self, venv_dir: str) -> None:
        """Ensure the virtual environment directory exists."""
        Path(venv_dir).mkdir(parents=True, exist_ok=True)
