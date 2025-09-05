"""Library directory for managing library candidates."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.managers.library_lifecycle.data_models import LibraryCandidate, LifecycleIssue
from griptape_nodes.retained_mode.managers.library_lifecycle.library_fsm import EvaluatedState, LibraryLifecycleFSM
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.library_lifecycle.data_models import LibraryEntry
    from griptape_nodes.retained_mode.managers.library_lifecycle.library_provenance import LibraryProvenance

logger = logging.getLogger("griptape_nodes")


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
        # Track library name conflicts centrally
        # Key: library name, Value: set of provenances with that name
        self._library_name_to_provenances: dict[str, set[LibraryProvenance]] = {}
        # Own all FSM instances for library lifecycle management
        self._provenance_to_fsm: dict[LibraryProvenance, LibraryLifecycleFSM] = {}

    async def discover_library(self, provenance: LibraryProvenance) -> None:
        """Discover a library and its provenance.

        Discovery is purely about cataloging - activation state is handled separately.
        """
        # Check if already discovered
        if provenance in self._discovered_libraries:
            return

        # Create entry with neutral active state (will be set by specific methods)
        entry = provenance.create_library_entry(active=False)
        self._discovered_libraries[provenance] = entry

        # Create FSM and run evaluation automatically
        await self._create_fsm_and_evaluate(provenance)

    async def add_curated_candidate(self, provenance: LibraryProvenance) -> None:
        """Add a curated library candidate.

        Curated libraries default to inactive and need to be activated by user.
        """
        await self.discover_library(provenance)

        # Set curated library as inactive by default
        if provenance in self._discovered_libraries:
            entry = self._discovered_libraries[provenance]
            entry.active = False

    async def add_user_candidate(self, provenance: LibraryProvenance) -> None:
        """Add a user-supplied library candidate.

        User libraries default to active.
        """
        await self.discover_library(provenance)

        # Set user library as active by default
        if provenance in self._discovered_libraries:
            entry = self._discovered_libraries[provenance]
            entry.active = True

    def get_all_candidates(self) -> list[LibraryCandidate]:
        """Get all known library candidates with their entries.

        Returns list of LibraryCandidate named tuples.
        """
        candidates = []
        for provenance, entry in self._discovered_libraries.items():
            candidates.append(LibraryCandidate(provenance=provenance, entry=entry))
        return candidates

    def get_active_candidates(self) -> list[LibraryCandidate]:
        """Get all candidates that should be active.

        Returns list of LibraryCandidate named tuples for active libraries.
        """
        all_candidates = self.get_all_candidates()
        return [candidate for candidate in all_candidates if candidate.entry.active]

    def get_candidate(self, provenance: LibraryProvenance) -> LibraryEntry | None:
        """Get a specific library candidate entry by provenance."""
        return self._discovered_libraries.get(provenance)

    def remove_candidate(self, provenance: LibraryProvenance) -> None:
        """Remove a library candidate from discovery."""
        self._discovered_libraries.pop(provenance, None)
        # Remove from name mapping
        for library_name, provenances in list(self._library_name_to_provenances.items()):
            provenances.discard(provenance)
            if not provenances:  # Remove empty sets
                del self._library_name_to_provenances[library_name]
        # Remove FSM
        self._provenance_to_fsm.pop(provenance, None)

    def clear(self) -> None:
        """Clear all library candidates."""
        self._discovered_libraries.clear()
        self._library_name_to_provenances.clear()
        self._provenance_to_fsm.clear()

    def get_discovered_libraries(self) -> dict[LibraryProvenance, LibraryEntry]:
        """Get all discovered libraries and their entries.

        Returns dict mapping provenance -> entry.
        """
        return self._discovered_libraries.copy()

    def get_conflicting_provenances(self, library_name: str) -> set[LibraryProvenance]:
        """Get all provenances that have the given library name.

        Returns empty set if library name not found.
        """
        return self._library_name_to_provenances.get(library_name, set()).copy()

    def has_library_name_conflicts(self, library_name: str) -> bool:
        """Check if a library name has conflicts (more than one provenance)."""
        return len(self._library_name_to_provenances.get(library_name, set())) > 1

    def get_all_conflicting_library_names(self) -> list[str]:
        """Get all library names that have conflicts."""
        return [name for name, provenances in self._library_name_to_provenances.items() if len(provenances) > 1]

    def can_install_library(self, provenance: LibraryProvenance, library_name: str) -> bool:  # noqa: ARG002
        """Check if a library can be installed (no name conflicts)."""
        return not self.has_library_name_conflicts(library_name)

    def get_conflicting_library_display_names(
        self, library_name: str, excluding_provenance: LibraryProvenance | None = None
    ) -> list[str]:
        """Get display names of libraries that conflict with the given library name.

        Optionally exclude a specific provenance from the results.
        """
        conflicting_provenances = self.get_conflicting_provenances(library_name)
        if excluding_provenance:
            conflicting_provenances.discard(excluding_provenance)
        return [p.get_display_name() for p in conflicting_provenances]

    def get_installable_candidates(self) -> list[LibraryCandidate]:
        """Get all active candidates that are ready for installation (evaluated, usable, no conflicts)."""
        active_candidates = self.get_active_candidates()
        return [
            candidate for candidate in active_candidates if not self.get_installation_blockers(candidate.provenance)
        ]

    def get_installation_blockers(self, provenance: LibraryProvenance) -> list[LifecycleIssue]:
        """Get all issues preventing this library from being installed."""
        blockers = []
        fsm = self._provenance_to_fsm.get(provenance)

        if not fsm:
            blockers.append(LifecycleIssue(message="No FSM found for library", severity=LibraryStatus.MISSING))
            return blockers

        # Check if library is in evaluated state
        if fsm.current_state != EvaluatedState:
            blockers.append(
                LifecycleIssue(
                    message=f"Library not in evaluated state: {fsm.get_current_state_name()}",
                    severity=LibraryStatus.UNUSABLE,
                )
            )
            return blockers

        context = fsm.get_context()

        # Check if inspection result is usable
        if not context.inspection_result or not context.inspection_result.is_usable():
            blockers.append(LifecycleIssue(message="Library has inspection issues", severity=LibraryStatus.UNUSABLE))
            return blockers

        # Check if schema is available
        if not context.inspection_result.schema:
            blockers.append(LifecycleIssue(message="Library schema not available", severity=LibraryStatus.UNUSABLE))
            return blockers

        # Check for name conflicts
        library_name = context.inspection_result.schema.name
        if self.has_library_name_conflicts(library_name):
            conflicting_libraries = self.get_conflicting_library_display_names(library_name, provenance)
            blockers.append(
                LifecycleIssue(
                    message=f"Library has name conflicts with: {conflicting_libraries}", severity=LibraryStatus.FLAWED
                )
            )

        return blockers

    async def _create_fsm_and_evaluate(self, provenance: LibraryProvenance) -> None:
        """Create FSM for provenance and run through evaluation phase.

        This method is called automatically when a library is discovered.
        """
        logger.debug("Creating FSM and starting evaluation for library: %s", provenance.get_display_name())

        # Create FSM instance for this library
        fsm = LibraryLifecycleFSM(provenance)
        self._provenance_to_fsm[provenance] = fsm

        # Start the lifecycle and run through evaluation
        await fsm.start_lifecycle()

        # Progress through inspection
        if fsm.can_begin_inspection():
            await fsm.begin_inspection()
        else:
            logger.error(
                "Cannot inspect library '%s' - inspection step cannot proceed",
                provenance.get_display_name(),
            )
            return

        # Progress through evaluation
        if fsm.can_begin_evaluation():
            await fsm.begin_evaluation()
        else:
            logger.error(
                "Cannot evaluate library '%s' - evaluation step cannot proceed",
                provenance.get_display_name(),
            )
            return

        # Update library name mapping after successful inspection and evaluation
        # At this point, we know inspection_result and schema are valid since we completed both phases
        context = fsm.get_context()
        if context.inspection_result and context.inspection_result.schema:
            library_name = context.inspection_result.schema.name
            if library_name not in self._library_name_to_provenances:
                self._library_name_to_provenances[library_name] = set()
            self._library_name_to_provenances[library_name].add(provenance)

        logger.debug("Completed FSM evaluation for library: %s", provenance.get_display_name())

    async def install_library(self, provenance: LibraryProvenance) -> bool:
        """Install a library by running its FSM through the installation phase.

        Returns True if installation was successful, False otherwise.
        """
        fsm = self._provenance_to_fsm.get(provenance)
        if not fsm:
            logger.error("No FSM found for provenance: %s", provenance.get_display_name())
            return False

        # Check if library has name conflicts that prevent installation
        context = fsm.get_context()
        if context.inspection_result and context.inspection_result.schema:
            library_name = context.inspection_result.schema.name
            if self.has_library_name_conflicts(library_name):
                conflicting_libraries = self.get_conflicting_library_display_names(library_name, provenance)
                logger.error(
                    "Cannot install library '%s' due to name conflicts with: %s",
                    provenance.get_display_name(),
                    conflicting_libraries,
                )
                return False

        # Proceed with installation
        if fsm.can_begin_installation():
            await fsm.begin_installation()
            logger.info("Installation completed for library: %s", provenance.get_display_name())
            return True
        logger.error(
            "Cannot install library '%s' - installation step cannot proceed",
            provenance.get_display_name(),
        )
        return False

    async def load_library(self, provenance: LibraryProvenance) -> bool:
        """Load a library by running its FSM through the loading phase.

        Returns True if loading was successful, False otherwise.
        """
        fsm = self._provenance_to_fsm.get(provenance)
        if not fsm:
            logger.error("No FSM found for provenance: %s", provenance.get_display_name())
            return False

        if not fsm.can_begin_loading():
            logger.error(
                "Cannot load library '%s' - loading step cannot proceed",
                provenance.get_display_name(),
            )
            return False

        # Proceed with loading
        await fsm.begin_loading()

        if not fsm.is_loaded():
            logger.error(
                "Failed to load library '%s' - did not reach loaded state: %s",
                provenance.get_display_name(),
                fsm.get_current_state_name(),
            )
            return False

        logger.info("Successfully loaded library '%s'", provenance.get_display_name())
        return True

    def get_library_name_from_provenance(self, provenance: LibraryProvenance) -> str | None:
        """Get the library name for a given provenance after evaluation.

        Returns None if the provenance hasn't been evaluated or doesn't have a valid schema.
        """
        fsm = self._provenance_to_fsm.get(provenance)
        if not fsm:
            return None

        context = fsm.get_context()
        if not context.inspection_result or not context.inspection_result.schema:
            return None

        return context.inspection_result.schema.name

    def get_provenances_for_library_name(self, library_name: str) -> list[LibraryProvenance]:
        """Get all provenances that have the given library name.

        Returns empty list if library name not found.
        """
        return list(self._library_name_to_provenances.get(library_name, set()))

    def find_provenance_by_library_name(self, library_name: str) -> LibraryProvenance | None:
        """Find a single provenance for a library name.

        Returns None if library name not found or if there are multiple provenances
        (indicating a conflict that should be resolved first).
        """
        provenances = self.get_provenances_for_library_name(library_name)
        if len(provenances) == 1:
            return provenances[0]
        return None
