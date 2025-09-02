"""Package library provenance implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

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


@dataclass(frozen=True)
class LibraryProvenancePackage(LibraryProvenance):
    """Reference to a package library."""

    requirement_specifier: str

    def get_display_name(self) -> str:
        """Get a human-readable name for this provenance."""
        return f"Package: {self.requirement_specifier}"

    def inspect(self) -> InspectionResult:
        """Inspect this package to extract schema and identify issues."""
        # TODO: Implement package inspection (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # This should:
        # 1. Check if package is available in PyPI or other repositories
        # 2. Download and inspect package metadata
        # 3. Extract library schema from package

        return InspectionResult(
            schema=None,
            issues=[
                LifecycleIssue(
                    message=f"Package inspection not yet implemented for {self.requirement_specifier}",
                    severity=LibraryStatus.UNUSABLE,
                )
            ],
        )

    def evaluate(self, context: LibraryLifecycleContext) -> EvaluationResult:  # noqa: ARG002
        """Evaluate this package for conflicts/issues."""
        issues = []
        issues.append(
            LifecycleIssue(
                message="Package evaluation not yet implemented",
                severity=LibraryStatus.UNUSABLE,
            )
        )
        return EvaluationResult(issues=issues)

    async def install(self, context: LibraryLifecycleContext) -> InstallationResult:  # noqa: ARG002
        """Install this package library."""
        issues = []
        issues.append(
            LifecycleIssue(
                message="Package installation not yet implemented",
                severity=LibraryStatus.UNUSABLE,
            )
        )

        # TODO: Implement package installation (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # This should:
        # 1. Create virtual environment
        # 2. Install package using pip
        # 3. Extract library files from installed package

        return InstallationResult(
            installation_path="",
            venv_path="",
            issues=issues,
        )

    def load_library(self, context: LibraryLifecycleContext) -> LibraryLoadedResult:  # noqa: ARG002
        """Load this package library into the registry."""
        issues = []
        issues.append(
            LifecycleIssue(
                message="Package loading not yet implemented",
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
