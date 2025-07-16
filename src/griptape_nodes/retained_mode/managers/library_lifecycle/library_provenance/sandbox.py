"""Sandbox library provenance implementation."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from griptape_nodes.node_library.library_registry import LibraryMetadata, LibrarySchema
from griptape_nodes.retained_mode.managers.library_lifecycle.data_models import (
    InspectionResult,
    InstallationData,
    LifecycleIssue,
    LoadedLibraryData,
)
from griptape_nodes.retained_mode.managers.library_lifecycle.library_provenance.base import LibraryProvenance
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus

logger = logging.getLogger("griptape_nodes")


class LibraryPreferenceSandbox(BaseModel):
    """Serializable preference for a sandbox library directory."""

    directory_path: str = Field(description="Path to the sandbox library directory")
    active: bool = Field(default=True, description="Whether this sandbox library is active")


@dataclass(frozen=True)
class LibraryProvenanceSandbox(LibraryProvenance):
    """Reference to a sandbox library (dynamically assembled from node files)."""

    sandbox_path: str

    def get_display_name(self) -> str:
        """Get a human-readable name for this provenance."""
        return f"Sandbox: {self.sandbox_path}"

    def inspect(self) -> InspectionResult:
        """Inspect this sandbox to dynamically create schema from node files."""
        if not self._validate_sandbox_path():
            return InspectionResult(
                schema=None,
                issues=[
                    LifecycleIssue(
                        message=f"Sandbox directory does not exist or is not readable: {self.sandbox_path}",
                        severity=LibraryStatus.UNUSABLE,
                    )
                ],
            )

        # TODO: Implement dynamic library schema creation from node files (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # This should:
        # 1. Scan the sandbox directory for Python files
        # 2. Extract node class definitions and metadata
        # 3. Dynamically create LibrarySchema with discovered nodes
        # 4. Generate appropriate categories and metadata

        # For now, return a basic schema structure
        # This is a placeholder that should be replaced with actual node discovery
        sandbox_name = Path(self.sandbox_path).name

        # Create minimal metadata for sandbox
        metadata = LibraryMetadata(
            author="Sandbox Developer",
            description=f"Dynamically discovered sandbox library from {sandbox_name}",
            library_version="dev",
            engine_version="1.0.0",
            tags=["sandbox", "development"],
        )

        # Create basic schema - this should be replaced with actual node discovery
        schema = LibrarySchema(
            name=sandbox_name,
            library_schema_version="1.0.0",
            metadata=metadata,
            categories=[],  # Should be populated from discovered nodes
            nodes=[],  # Should be populated from discovered nodes
        )

        return InspectionResult(schema=schema, issues=[])

    def evaluate(self) -> list[str]:
        """Evaluate this sandbox for conflicts/issues."""
        problems = []

        # Check if sandbox is still accessible
        if not self._validate_sandbox_path():
            problems.append(f"Sandbox directory is no longer accessible: {self.sandbox_path}")
            return problems

        # TODO: Add sandbox-specific evaluation logic (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # This could include:
        # - Checking for naming conflicts with existing libraries
        # - Validating node implementations
        # - Checking for missing dependencies

        return problems

    def install(self, library_name: str) -> InstallationData:  # noqa: ARG002
        """Install this sandbox library."""
        problems = []

        # Sandbox libraries don't need complex installation
        # They're loaded directly from the sandbox directory
        return InstallationData(
            installation_path=self.sandbox_path,
            venv_path="",
            installation_problems=problems,
        )

    def load_library(self, library_schema: LibrarySchema) -> LoadedLibraryData:
        """Load this sandbox library into the registry."""
        problems = []

        if not library_schema.metadata:
            problems.append("No metadata available for loading")

        # TODO: Actually register the sandbox library with the LibraryRegistry (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # This would involve:
        # 1. Creating a Library instance from the dynamically discovered nodes
        # 2. Adding it to the LibraryRegistry
        # 3. Handling any registration conflicts or errors

        return LoadedLibraryData(
            metadata=library_schema.metadata
            or LibraryMetadata(
                author="unknown", description="unknown", library_version="unknown", engine_version="unknown", tags=[]
            ),
            load_problems=problems,
            enabled=True,
            name_override=None,
        )

    def _validate_sandbox_path(self) -> bool:
        """Validate that the sandbox path exists and is readable."""
        try:
            path = Path(self.sandbox_path)
            return path.exists() and path.is_dir() and os.access(path, os.R_OK)
        except Exception as e:
            logger.error("Failed to validate sandbox path %s: %s", self.sandbox_path, e)
            return False
