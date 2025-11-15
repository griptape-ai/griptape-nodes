"""Local file library provenance implementation."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError

from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
from griptape_nodes.retained_mode.events.config_events import (
    GetConfigCategoryRequest,
    GetConfigCategoryResultSuccess,
    SetConfigCategoryRequest,
    SetConfigCategoryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.library_lifecycle.data_models import (
    EvaluationResult,
    InspectionResult,
    InstallationResult,
    LibraryLoadedResult,
    LifecycleIssue,
)
from griptape_nodes.retained_mode.managers.library_lifecycle.library_provenance.base import LibraryProvenance
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.utils.async_utils import subprocess_run

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.library_lifecycle.library_fsm import LibraryLifecycleContext

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
        issues = []

        # File system validation
        if not self._validate_file_exists():
            issues.append(
                LifecycleIssue(
                    message=f"Library file does not exist or is not readable: {self.file_path}",
                    severity=LibraryStatus.UNUSABLE,
                )
            )
            return InspectionResult(schema=None, issues=issues)

        # Schema validation
        try:
            with Path(self.file_path).open(encoding="utf-8") as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as e:
            issues.append(LifecycleIssue(message=f"Invalid JSON in library file: {e}", severity=LibraryStatus.UNUSABLE))
            return InspectionResult(schema=None, issues=issues)
        except Exception as e:
            issues.append(LifecycleIssue(message=f"Failed to read library file: {e}", severity=LibraryStatus.UNUSABLE))
            return InspectionResult(schema=None, issues=issues)

        # Validate library schema structure
        try:
            schema = LibrarySchema.model_validate(raw_data)
        except ValidationError as e:
            for error in e.errors():
                loc = " -> ".join(map(str, error["loc"]))
                msg = error["msg"]
                error_type = error["type"]
                problem = f"Error in section '{loc}': {error_type}, {msg}"
                issues.append(LifecycleIssue(message=problem, severity=LibraryStatus.UNUSABLE))
            return InspectionResult(schema=None, issues=issues)

        return InspectionResult(schema=schema, issues=issues)

    def evaluate(self, context: LibraryLifecycleContext) -> EvaluationResult:
        """Evaluate this local file for conflicts/issues."""
        issues = []

        # Get schema from context (guaranteed to be valid at this point)
        assert context.inspection_result is not None  # noqa: S101
        schema = context.inspection_result.schema
        assert schema is not None  # noqa: S101

        # Version compatibility validation
        version_issues = GriptapeNodes.VersionCompatibilityManager().check_library_version_compatibility(schema)
        for issue in version_issues:
            lifecycle_severity = LibraryStatus(issue.severity.value)
            # Collate the problem to get the display message
            problem_message = type(issue.problem).collate_problems_for_display([issue.problem])
            issues.append(LifecycleIssue(message=problem_message, severity=lifecycle_severity))

        # NOTE: Library name conflicts are checked at the manager level
        # across all evaluated libraries, not here

        return EvaluationResult(issues=issues)

    async def install(self, context: LibraryLifecycleContext) -> InstallationResult:
        """Install this local file library."""
        problems = []
        venv_path = ""

        # Get the LibraryManager instance to use its methods
        library_manager = GriptapeNodes.LibraryManager()

        # Get library schema from context (guaranteed to be valid at this point)
        assert context.inspection_result is not None  # noqa: S101
        library_data = context.inspection_result.schema
        assert library_data is not None  # noqa: S101

        # If no dependencies are specified, early out
        if not (
            library_data.metadata
            and library_data.metadata.dependencies
            and library_data.metadata.dependencies.pip_dependencies
        ):
            return InstallationResult(
                installation_path=self.file_path,
                venv_path="",
                issues=problems,
            )

        pip_install_flags = library_data.metadata.dependencies.pip_install_flags
        if pip_install_flags is None:
            pip_install_flags = []
        pip_dependencies = library_data.metadata.dependencies.pip_dependencies

        # Determine venv path for dependency installation
        venv_path = library_manager._get_library_venv_path(library_data.name, self.file_path)

        # Only install dependencies if conditions are met
        library_venv_python_path = None
        try:
            library_venv_python_path = await library_manager._init_library_venv(venv_path)
        except RuntimeError as e:
            problems.append(
                LifecycleIssue(
                    message=str(e),
                    severity=LibraryStatus.UNUSABLE,
                )
            )
            # Return early for blocking issues
            return InstallationResult(
                installation_path=self.file_path,
                venv_path=str(venv_path) if venv_path else "",
                issues=problems,
            )

        if library_venv_python_path and library_manager._can_write_to_venv_location(library_venv_python_path):
            # Check disk space before installing dependencies
            config_manager = GriptapeNodes.ConfigManager()
            min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_libraries")
            if not OSManager.check_available_disk_space(Path(venv_path), min_space_gb):
                error_msg = OSManager.format_disk_space_error(Path(venv_path))
                problems.append(
                    LifecycleIssue(
                        message=f"Insufficient disk space for dependencies (requires {min_space_gb} GB): {error_msg}",
                        severity=LibraryStatus.UNUSABLE,
                    )
                )
                # Return early for blocking issues
                return InstallationResult(
                    installation_path=self.file_path,
                    venv_path=str(venv_path) if venv_path else "",
                    issues=problems,
                )

            # Grab the python executable from the virtual environment so that we can pip install there
            logger.info("Installing dependencies for library '%s' with pip in venv at %s", library_data.name, venv_path)
            try:
                await subprocess_run(
                    [
                        sys.executable,
                        "-m",
                        "uv",
                        "pip",
                        "install",
                        *pip_dependencies,
                        *pip_install_flags,
                        "--python",
                        str(library_venv_python_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                error_details = f"return code={e.returncode}, stdout={e.stdout}, stderr={e.stderr}"
                problems.append(
                    LifecycleIssue(
                        message=f"Dependency installation failed: {error_details}",
                        severity=LibraryStatus.FLAWED,
                    )
                )
        elif library_venv_python_path:
            logger.debug(
                "Skipping dependency installation for library '%s' - venv location at %s is not writable",
                library_data.name,
                venv_path,
            )

        return InstallationResult(
            installation_path=self.file_path,
            venv_path=str(venv_path) if venv_path else "",
            issues=problems,
        )

    def load_library(self, context: LibraryLifecycleContext) -> LibraryLoadedResult:  # noqa: C901
        """Load this local file library into the registry."""
        issues = []

        # Get the LibraryManager instance to use its methods
        library_manager = GriptapeNodes.LibraryManager()

        # Get library schema from context (guaranteed to be valid at this point)
        assert context.inspection_result is not None  # noqa: S101
        library_data = context.inspection_result.schema
        assert library_data is not None  # noqa: S101

        # Use the file path from this provenance
        file_path = self.file_path
        base_dir = Path(file_path).parent

        # Load advanced library module if specified
        advanced_library_instance = None
        if library_data.advanced_library_path:
            try:
                advanced_library_instance = library_manager._load_advanced_library_module(
                    library_data=library_data,
                    base_dir=base_dir,
                )
            except Exception as err:
                issues.append(
                    LifecycleIssue(
                        message=f"Failed to load Advanced Library module from '{library_data.advanced_library_path}': {err}",
                        severity=LibraryStatus.UNUSABLE,
                    )
                )
                return LibraryLoadedResult(issues=issues)

        # Create or get the library
        library = None
        try:
            # Try to create a new library
            library = LibraryRegistry.generate_new_library(
                library_data=library_data,
                mark_as_default_library=False,  # TODO(#1234): determine if this should be configurable
                advanced_library=advanced_library_instance,
            )
        except KeyError:
            # Library already exists
            issues.append(
                LifecycleIssue(
                    message="Failed because a library with this name was already registered. Check the Settings to ensure duplicate libraries are not being loaded.",
                    severity=LibraryStatus.UNUSABLE,
                )
            )
            return LibraryLoadedResult(issues=issues)

        # Handle library settings
        if library_data.settings is not None:
            # Assign them into the config space
            for library_data_setting in library_data.settings:
                # Does the category exist?
                get_category_request = GetConfigCategoryRequest(category=library_data_setting.category)
                get_category_result = GriptapeNodes.handle_request(get_category_request)
                if not isinstance(get_category_result, GetConfigCategoryResultSuccess):
                    # That's OK, we'll invent it. Or at least we'll try.
                    create_new_category_request = SetConfigCategoryRequest(
                        category=library_data_setting.category, contents=library_data_setting.contents
                    )
                    create_new_category_result = GriptapeNodes.handle_request(create_new_category_request)
                    if not isinstance(create_new_category_result, SetConfigCategoryResultSuccess):
                        issues.append(
                            LifecycleIssue(
                                message=f"Failed to create new config category '{library_data_setting.category}'.",
                                severity=LibraryStatus.FLAWED,
                            )
                        )
                        continue  # SKIP IT
                else:
                    # We had an existing category. Union our changes into it (not replacing anything that matched).
                    existing_category_contents = get_category_result.contents
                    existing_category_contents.update(library_data_setting.contents)
                    set_category_request = SetConfigCategoryRequest(
                        category=library_data_setting.category, contents=existing_category_contents
                    )
                    set_category_result = GriptapeNodes.handle_request(set_category_request)
                    if not isinstance(set_category_result, SetConfigCategoryResultSuccess):
                        issues.append(
                            LifecycleIssue(
                                message=f"Failed to update config category '{library_data_setting.category}'.",
                                severity=LibraryStatus.FLAWED,
                            )
                        )
                        continue  # SKIP IT

        # Get library version from schema metadata
        library_version = library_data.metadata.library_version

        # Add the directory to the Python path to allow for relative imports
        sys.path.insert(0, str(base_dir))

        # Attempt to load nodes from the library
        library_load_results = library_manager._attempt_load_nodes_from_library(
            library_data=library_data,
            library=library,
            base_dir=base_dir,
            library_file_path=file_path,
            library_version=library_version,
            problems=[],  # We'll handle problems through issues instead
        )

        # Convert any problems from library_load_results to issues
        if library_load_results.problems:
            # Group problems by type and collate them for display
            problems_by_type = defaultdict(list)
            for problem in library_load_results.problems:
                problems_by_type[type(problem)].append(problem)

            # Collate each group
            collated_strings = []
            for problem_class, instances in problems_by_type.items():
                collated_display = problem_class.collate_problems_for_display(instances)
                collated_strings.append(collated_display)

            collated_problems = "\n".join(collated_strings)
            issues.append(
                LifecycleIssue(
                    message=collated_problems,
                    severity=library_load_results.status,
                )
            )

        return LibraryLoadedResult(issues=issues)

    def _validate_file_exists(self) -> bool:
        """Validate that the library file exists and is readable."""
        try:
            path = Path(self.file_path)
            return path.exists() and path.is_file() and os.access(path, os.R_OK)
        except Exception as e:
            logger.error("Failed to validate file %s: %s", self.file_path, e)
            return False
