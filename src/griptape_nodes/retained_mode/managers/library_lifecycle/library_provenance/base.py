"""Abstract base class for library provenance."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.managers.library_lifecycle.data_models import (
    EvaluationResult,
    InspectionResult,
    InstallationResult,
    LibraryEntry,
    LibraryLoadedResult,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.library_lifecycle.library_fsm import LibraryLifecycleContext


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
    def evaluate(self, context: LibraryLifecycleContext) -> EvaluationResult:
        """Evaluate this provenance for conflicts/issues.

        Args:
            context: Lifecycle context containing inspection results

        Returns:
            EvaluationResult with structured issues and severity levels
        """

    @abstractmethod
    async def install(self, context: LibraryLifecycleContext) -> InstallationResult:
        """Install this provenance.

        Args:
            context: Lifecycle context containing inspection results

        Returns:
            InstallationResult with structured issues and severity levels
        """

    @abstractmethod
    def load_library(self, context: LibraryLifecycleContext) -> LibraryLoadedResult:
        """Load this provenance into the registry.

        Args:
            context: Lifecycle context containing inspection results

        Returns:
            LibraryLoadedResult with structured issues and severity levels
        """
