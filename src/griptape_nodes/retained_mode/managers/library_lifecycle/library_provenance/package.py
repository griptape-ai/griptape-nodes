"""Package library provenance implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xdg_base_dirs import xdg_data_home

from griptape_nodes.node_library.library_registry import LibraryMetadata, LibrarySchema
from griptape_nodes.retained_mode.managers.library_lifecycle.data_models import (
    InspectionResult,
    InstallationData,
    LifecycleIssue,
    LoadedLibraryData,
)
from griptape_nodes.retained_mode.managers.library_lifecycle.library_provenance.base import LibraryProvenance
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus


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

    def evaluate(self) -> list[str]:
        """Evaluate this package for conflicts/issues."""
        problems = []
        problems.append("Package evaluation not yet implemented")
        return problems

    def install(self, library_name: str) -> InstallationData:  # noqa: ARG002
        """Install this package library."""
        problems = []
        problems.append("Package installation not yet implemented")

        # TODO: Implement package installation (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # This should:
        # 1. Create virtual environment
        # 2. Install package using pip
        # 3. Extract library files from installed package

        return InstallationData(
            installation_path="",
            venv_path="",
            installation_problems=problems,
        )

    def load_library(self, library_schema: LibrarySchema) -> LoadedLibraryData:
        """Load this package library into the registry."""
        problems = []
        problems.append("Package loading not yet implemented")

        return LoadedLibraryData(
            metadata=library_schema.metadata
            or LibraryMetadata(
                author="unknown", description="unknown", library_version="unknown", engine_version="unknown", tags=[]
            ),
            load_problems=problems,
            enabled=True,
            name_override=None,
        )

    def _get_base_venv_directory(self) -> str:
        """Get the base directory for virtual environments."""
        return str(xdg_data_home() / "griptape_nodes" / "library_venvs")

    def _ensure_venv_directory_exists(self, venv_dir: str) -> None:
        """Ensure the virtual environment directory exists."""
        Path(venv_dir).mkdir(parents=True, exist_ok=True)
