"""Local file library provenance implementation."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
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

logger = logging.getLogger("griptape_nodes")


class LibraryPreferenceLocalFile(BaseModel):
    """Serializable preference for a local file library."""

    file_path: str = Field(description="Path to the library file")
    active: bool = Field(default=True, description="Whether this local file library is active")


@dataclass(frozen=True)
class LibraryProvenanceLocalFile(LibraryProvenance):
    """Reference to a local file library."""

    file_path: str

    def get_display_name(self) -> str:
        """Get a human-readable name for this provenance."""
        return f"Local file: {self.file_path}"

    def inspect(self) -> InspectionResult:
        """Inspect this local file to extract schema and identify issues."""
        return self._inspect_library_schema()

    def evaluate(self) -> list[str]:
        """Evaluate this local file for conflicts/issues."""
        problems = []

        # Check if file is still accessible
        if not self._validate_file_exists():
            problems.append(f"Library file is no longer accessible: {self.file_path}")
            return problems

        # Local files don't typically have conflicts
        return problems

    def install(self, library_name: str) -> InstallationData:
        """Install this local file library."""
        problems = []

        # Ensure base venv directory exists
        base_venv_dir = self._get_base_venv_directory()
        self._ensure_venv_directory_exists(base_venv_dir)

        # Create virtual environment
        venv_path, venv_problems = self._create_venv_if_needed(library_name, base_venv_dir)
        problems.extend(venv_problems)

        # Install dependencies
        dep_problems = self._install_dependencies(venv_path)
        problems.extend(dep_problems)

        return InstallationData(
            installation_path=self.file_path,
            venv_path=venv_path,
            installation_problems=problems,
        )

    def load_library(self, library_schema: LibrarySchema) -> LoadedLibraryData:
        """Load this local file library into the registry."""
        problems = []

        if not library_schema.metadata:
            problems.append("No metadata available for loading")

        # TODO: Actually register the library with the LibraryRegistry (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # This would involve:
        # 1. Creating a Library instance from the metadata
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

    def _validate_file_exists(self) -> bool:
        """Validate that the library file exists and is readable."""
        try:
            path = Path(self.file_path)
            return path.exists() and path.is_file() and os.access(path, os.R_OK)
        except Exception as e:
            logger.error("Failed to validate file %s: %s", self.file_path, e)
            return False

    def _inspect_library_schema(self) -> InspectionResult:
        """Inspect and validate library schema from the local file."""
        issues = []

        if not self._validate_file_exists():
            return InspectionResult(
                schema=None,
                issues=[
                    LifecycleIssue(
                        message=f"Library file does not exist or is not readable: {self.file_path}",
                        severity=LibraryStatus.UNUSABLE,
                    )
                ],
            )

        try:
            with Path(self.file_path).open(encoding="utf-8") as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as e:
            return InspectionResult(
                schema=None,
                issues=[LifecycleIssue(message=f"Invalid JSON in library file: {e}", severity=LibraryStatus.UNUSABLE)],
            )
        except Exception as e:
            return InspectionResult(
                schema=None,
                issues=[LifecycleIssue(message=f"Failed to read library file: {e}", severity=LibraryStatus.UNUSABLE)],
            )

        # Validate library schema
        try:
            library_schema = LibrarySchema.model_validate(raw_data)
        except ValidationError as e:
            return InspectionResult(
                schema=None,
                issues=[LifecycleIssue(message=f"Invalid library schema: {e}", severity=LibraryStatus.UNUSABLE)],
            )

        # Schema validation successful - metadata is guaranteed to be present
        # (Pydantic validation would have failed if metadata was missing)
        return InspectionResult(schema=library_schema, issues=issues)

    def _install_dependencies(self, venv_path: str) -> list[str]:  # noqa: C901
        """Install dependencies for the local file library."""
        problems = []

        # Load metadata to get dependencies
        inspection_result = self._inspect_library_schema()
        if inspection_result.issues:
            problems.extend([issue.message for issue in inspection_result.issues])
            return problems

        if (
            not inspection_result.schema
            or not inspection_result.schema.metadata
            or not inspection_result.schema.metadata.dependencies
        ):
            # No dependencies to install
            return problems

        dependencies = inspection_result.schema.metadata.dependencies
        if not dependencies.pip_dependencies:
            # No pip dependencies
            return problems

        # Install pip dependencies in the virtual environment
        python_exe = Path(venv_path) / "bin" / "python"
        if not python_exe.exists():
            # Try Windows path
            python_exe = Path(venv_path) / "Scripts" / "python.exe"

        if not python_exe.exists():
            problems.append(f"Python executable not found in venv: {venv_path}")
            return problems

        for dep in dependencies.pip_dependencies:
            try:
                cmd = [str(python_exe), "-m", "pip", "install", dep]
                if dependencies.pip_install_flags:
                    cmd.extend(dependencies.pip_install_flags)

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)  # noqa: S603
                if result.returncode != 0:
                    problems.append(f"Failed to install dependency {dep}: {result.stderr}")

            except subprocess.TimeoutExpired:
                problems.append(f"Timeout installing dependency {dep}")
            except Exception as e:
                problems.append(f"Error installing dependency {dep}: {e}")

        return problems

    def _create_venv_if_needed(self, library_name: str, base_venv_dir: str) -> tuple[str, list[str]]:
        """Create a virtual environment for the library if needed."""
        problems = []
        venv_path = Path(base_venv_dir) / f"library_{library_name}"

        if venv_path.exists():
            # Virtual environment already exists
            return str(venv_path), problems

        try:
            # Create virtual environment
            result = subprocess.run(  # noqa: S603
                [sys.executable, "-m", "venv", str(venv_path)], capture_output=True, text=True, timeout=120, check=False
            )

            if result.returncode != 0:
                problems.append(f"Failed to create virtual environment: {result.stderr}")
                return str(venv_path), problems

            logger.info("Created virtual environment for library %s at %s", library_name, venv_path)

        except subprocess.TimeoutExpired:
            problems.append("Timeout creating virtual environment")
        except Exception as e:
            problems.append(f"Error creating virtual environment: {e}")

        return str(venv_path), problems

    def _get_base_venv_directory(self) -> str:
        """Get the base directory for virtual environments."""
        return str(xdg_data_home() / "griptape_nodes" / "library_venvs")

    def _ensure_venv_directory_exists(self, venv_dir: str) -> None:
        """Ensure the virtual environment directory exists."""
        Path(venv_dir).mkdir(parents=True, exist_ok=True)
