"""Data models for library lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema
    from griptape_nodes.retained_mode.managers.library_lifecycle.library_provenance import LibraryProvenance


class LibraryByType(NamedTuple):
    """A library entry with its name, organized by provenance type."""

    name: str
    entry: LibraryEntry


class LibraryCandidate(NamedTuple):
    """A library candidate with its provenance and entry."""

    provenance: LibraryProvenance
    entry: LibraryEntry


@dataclass
class LifecycleIssue:
    """Represents an issue found during library lifecycle with severity level."""

    message: str
    severity: LibraryStatus


@dataclass
class Result:
    """Base class for all library lifecycle result objects."""

    issues: list[LifecycleIssue] = field(default_factory=list)

    def get_status(self) -> LibraryStatus:
        """Determine overall status based on issues."""
        if any(issue.severity == LibraryStatus.UNUSABLE for issue in self.issues):
            return LibraryStatus.UNUSABLE
        if any(issue.severity == LibraryStatus.FLAWED for issue in self.issues):
            return LibraryStatus.FLAWED
        return LibraryStatus.GOOD

    def is_usable(self) -> bool:
        """Check if result is usable despite issues."""
        return self.get_status() in [LibraryStatus.GOOD, LibraryStatus.FLAWED]


@dataclass
class InspectionResult(Result):
    """Result of library inspection with structured issues and severity levels."""

    schema: LibrarySchema | None = None

    def __init__(self, schema: LibrarySchema | None = None, issues: list[LifecycleIssue] | None = None):
        super().__init__(issues=issues or [])
        self.schema = schema

    def get_status(self) -> LibraryStatus:
        """Determine overall status based on issues and schema availability."""
        if not self.schema:
            return LibraryStatus.UNUSABLE
        return super().get_status()


@dataclass
class EvaluationResult(Result):
    """Result of library evaluation with structured issues and severity levels."""

    def __init__(self, issues: list[LifecycleIssue] | None = None):
        super().__init__(issues=issues or [])


@dataclass
class InstallationResult(Result):
    """Result of library installation with structured issues and severity levels."""

    installation_path: str = ""  # Where the library files are
    venv_path: str = ""  # Where the virtual environment is

    def __init__(self, installation_path: str = "", venv_path: str = "", issues: list[LifecycleIssue] | None = None):
        super().__init__(issues=issues or [])
        self.installation_path = installation_path
        self.venv_path = venv_path


@dataclass
class LibraryLoadedResult(Result):
    """Result of library loading with structured issues and severity levels."""

    def __init__(self, issues: list[LifecycleIssue] | None = None):
        super().__init__(issues=issues or [])


@dataclass
class LibraryEntry:
    """A library entry combining provenance and user configuration."""

    # Abstract base - concrete implementations in library_provenance.py
    active: bool = True
    library_name: str | None = None  # Set after inspection from metadata

    def get_provenance(self) -> LibraryProvenance:
        """Get the provenance for this library entry."""
        msg = "Subclasses must implement get_provenance()"
        raise NotImplementedError(msg)

    def set_library_name(self, name: str) -> None:
        """Set the library name after inspection."""
        self.library_name = name


@dataclass
class LibraryPreferences:
    """User preferences and configuration for libraries."""

    libraries: dict[str, LibraryEntry] = field(default_factory=dict)

    def add_library(self, name: str, library_entry: LibraryEntry) -> None:
        """Add or update a library entry."""
        library_entry.set_library_name(name)
        self.libraries[name] = library_entry

    def add_inspected_library(self, library_entry: LibraryEntry) -> str | None:
        """Add a library entry that has been inspected and has a library name.

        Returns the final library name used, or None if there was a conflict.
        """
        if not library_entry.library_name:
            msg = "Library entry must have a library_name set after inspection"
            raise ValueError(msg)

        library_name = library_entry.library_name

        # Check for conflicts
        if library_name in self.libraries:
            # Library name already exists - this is a conflict
            existing_entry = self.libraries[library_name]
            if existing_entry.get_provenance() != library_entry.get_provenance():
                # Different provenance with same name - this is a real conflict
                return None

        # No conflict, add the library
        self.libraries[library_name] = library_entry
        return library_name

    def has_library_entry(self, name: str) -> bool:
        """Check if a library entry exists."""
        return name in self.libraries

    def get_library_entry(self, name: str) -> LibraryEntry:
        """Get the library entry for a library."""
        if name not in self.libraries:
            msg = f"Library {name} not found in preferences"
            raise KeyError(msg)
        return self.libraries[name]

    def get_all_library_names(self) -> list[str]:
        """Get all library names in preferences."""
        return list(self.libraries.keys())

    def remove_library(self, name: str) -> None:
        """Remove a library from preferences."""
        self.libraries.pop(name, None)

    def get_libraries_by_type(self, provenance_type: type) -> list[LibraryByType]:
        """Get all libraries that have a specific provenance type."""
        matching_libraries = []

        for name, entry in self.libraries.items():
            if isinstance(entry.get_provenance(), provenance_type):
                matching_libraries.append(LibraryByType(name=name, entry=entry))

        return matching_libraries

    def get_libraries_by_provenance(self, provenance: LibraryProvenance) -> list[LibraryByType]:
        """Get all libraries that have a specific provenance."""
        matching_libraries = []

        for name, entry in self.libraries.items():
            if entry.get_provenance() == provenance:
                matching_libraries.append(LibraryByType(name=name, entry=entry))

        return matching_libraries
