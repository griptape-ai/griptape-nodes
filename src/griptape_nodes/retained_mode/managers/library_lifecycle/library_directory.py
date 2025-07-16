"""Library directory for managing library candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data_models import LibraryEntry
    from .library_provenance import LibraryProvenance


class LibraryDirectory:
    """Unified registry of all known libraries - both curated and user-added.

    This class manages discovery of libraries and works with LibraryPreferences
    for configuration. It's responsible for finding libraries and their provenances,
    while LibraryPreferences handles user configuration.
    """

    def __init__(self) -> None:
        # This is now just a discovery mechanism - the actual configuration
        # lives in LibraryPreferences
        # Key: provenance, Value: entry
        self._discovered_libraries: dict[LibraryProvenance, LibraryEntry] = {}

    def discover_library(self, provenance: LibraryProvenance) -> LibraryProvenance:
        """Discover a library and its provenance.

        Returns the provenance object for the discovered library.
        Discovery is purely about cataloging - activation state is handled separately.
        """
        # Check if already discovered
        if provenance in self._discovered_libraries:
            return provenance

        # Create entry with neutral active state (will be set by specific methods)
        entry = provenance.create_library_entry(active=False)
        self._discovered_libraries[provenance] = entry
        return provenance

    def add_curated_candidate(self, provenance: LibraryProvenance) -> LibraryProvenance:
        """Add a curated library candidate.

        Returns the provenance object for the added library.
        Curated libraries default to inactive and need to be activated by user.
        """
        self.discover_library(provenance)

        # Set curated library as inactive by default
        if provenance in self._discovered_libraries:
            entry = self._discovered_libraries[provenance]
            entry.active = False

        return provenance

    def add_user_candidate(self, provenance: LibraryProvenance) -> LibraryProvenance:
        """Add a user-supplied library candidate.

        Returns the provenance object for the added library.
        User libraries default to active.
        """
        self.discover_library(provenance)

        # Set user library as active by default
        if provenance in self._discovered_libraries:
            entry = self._discovered_libraries[provenance]
            entry.active = True

        return provenance

    def get_all_candidates(self) -> list[tuple[LibraryProvenance, LibraryEntry]]:
        """Get all known library candidates with their entries.

        Returns list of (provenance, entry) tuples.
        """
        candidates = []
        for provenance, entry in self._discovered_libraries.items():
            candidates.append((provenance, entry))
        return candidates

    def get_active_candidates(self) -> list[tuple[LibraryProvenance, LibraryEntry]]:
        """Get all candidates that should be active.

        Returns list of (provenance, entry) tuples for active libraries.
        """
        all_candidates = self.get_all_candidates()
        return [(provenance, entry) for provenance, entry in all_candidates if entry.active]

    def get_candidate(self, provenance: LibraryProvenance) -> LibraryEntry | None:
        """Get a specific library candidate entry by provenance."""
        return self._discovered_libraries.get(provenance)

    def remove_candidate(self, provenance: LibraryProvenance) -> None:
        """Remove a library candidate from discovery."""
        self._discovered_libraries.pop(provenance, None)

    def clear(self) -> None:
        """Clear all library candidates."""
        self._discovered_libraries.clear()

    def get_discovered_libraries(self) -> dict[LibraryProvenance, LibraryEntry]:
        """Get all discovered libraries and their entries.

        Returns dict mapping provenance -> entry.
        """
        return self._discovered_libraries.copy()
