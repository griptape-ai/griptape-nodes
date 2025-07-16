"""Abstract base class for library provenance."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.managers.library_lifecycle.data_models import (
    InspectionResult,
    InstallationData,
    LibraryEntry,
    LoadedLibraryData,
)

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema


@dataclass(frozen=True)
class LibraryProvenance(ABC):
    """Pure reference to a library source."""

    def get_display_name(self) -> str:
        """Get a human-readable name for this provenance."""
        return f"Unknown provenance: {type(self).__name__}"

    def create_library_entry(self, *, active: bool = True) -> LibraryEntry:
        """Create a library entry for this provenance."""

        # Create a basic library entry that includes this provenance
        class BasicLibraryEntry(LibraryEntry):
            def __init__(self, provenance: LibraryProvenance, *, active: bool = True):
                super().__init__(active=active)
                self._provenance = provenance

            def get_provenance(self) -> LibraryProvenance:
                return self._provenance

        return BasicLibraryEntry(self, active=active)

    @abstractmethod
    def inspect(self) -> InspectionResult:
        """Inspect this provenance to extract schema and identify issues.

        Returns:
            InspectionResult with schema and categorized issues
        """

    @abstractmethod
    def evaluate(self) -> list[str]:
        """Evaluate this provenance for conflicts/issues.

        Returns:
            List of problems encountered during evaluation
        """

    @abstractmethod
    def install(self, library_name: str) -> InstallationData:
        """Install this provenance.

        Args:
            library_name: The library name from inspection, if available

        Returns:
            Installation data with paths and any problems
        """

    @abstractmethod
    def load_library(self, library_schema: LibrarySchema) -> LoadedLibraryData:
        """Load this provenance into the registry.

        Args:
            library_schema: The library schema from inspection containing name and metadata

        Returns:
            Loaded library data with any problems
        """
