"""Library lifecycle finite state machine implementation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.retained_mode.managers.library_lifecycle.data_models import (
    EvaluationResult,
    InspectionResult,
    InstallationResult,
    LibraryLoadedResult,
    LifecycleIssue,
)
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema
    from griptape_nodes.retained_mode.managers.library_lifecycle.library_provenance import LibraryProvenance

StateType = type[State]

logger = logging.getLogger("griptape_nodes")


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_state: StateType | None, requested_state: StateType, reason: str):
        self.current_state = current_state
        self.requested_state = requested_state
        self.reason = reason
        current_name = current_state.__name__ if current_state else "None"
        super().__init__(f"Cannot transition from {current_name} to {requested_state.__name__}: {reason}")


@dataclass
class LibraryLifecycleContext:
    """Context object for library lifecycle state machine."""

    # Core identity
    provenance: LibraryProvenance

    # State machine data populated as we progress
    inspection_result: InspectionResult | None = None
    evaluation_result: EvaluationResult | None = None
    installation_result: InstallationResult | None = None
    library_loaded_result: LibraryLoadedResult | None = None

    def get_library_schema(self) -> LibrarySchema | None:
        """Get the library schema from inspection result."""
        return self.inspection_result.schema if self.inspection_result else None

    def get_inspection_issues(self) -> list[LifecycleIssue]:
        """Get inspection issues from inspection result."""
        return self.inspection_result.issues if self.inspection_result else []

    def get_evaluation_issues(self) -> list[LifecycleIssue]:
        """Get evaluation issues from evaluation result."""
        return self.evaluation_result.issues if self.evaluation_result else []

    def get_installation_issues(self) -> list[LifecycleIssue]:
        """Get installation issues from installation result."""
        return self.installation_result.issues if self.installation_result else []

    def get_library_loaded_issues(self) -> list[LifecycleIssue]:
        """Get library loaded issues from library loaded result."""
        return self.library_loaded_result.issues if self.library_loaded_result else []

    def get_effective_active_state(self) -> bool:
        """Get the effective active state for this library."""
        # TODO: Implement proper integration with LibraryPreferences from data_models (https://github.com/griptape-ai/griptape-nodes/issues/1234)
        # For now, return True as a fallback until the proper integration is implemented
        # This method should:
        # 1. Get the runtime library preferences (not the settings preferences)
        # 2. Check if library is active by name or provenance
        # 3. Return appropriate active state
        return True


# States for the Library Lifecycle FSM


class CandidateState(State):
    """Initial state where we have a library candidate ready for processing."""

    @staticmethod
    async def on_enter(context: LibraryLifecycleContext) -> StateType | None:
        logger.info("Library %s is now a candidate for processing", context.provenance.get_display_name())
        return None  # Wait for explicit transition to InspectingState

    @staticmethod
    def get_allowed_transitions_for_context(context: LibraryLifecycleContext) -> set[StateType]:  # noqa: ARG004
        """Get context-specific allowed transitions."""
        return {InspectingState}


class InspectingState(State):
    """State where we inspect the library to gather metadata."""

    @staticmethod
    def get_allowed_transitions_for_context(context: LibraryLifecycleContext) -> set[StateType]:  # noqa: ARG004
        """Get context-specific allowed transitions."""
        return {InspectedState}

    @staticmethod
    async def on_enter(context: LibraryLifecycleContext) -> StateType | None:
        logger.info("Inspecting library %s", context.provenance.get_display_name())

        # Store inspection result directly
        context.inspection_result = context.provenance.inspect()

        if context.inspection_result.schema:
            # Library name is now accessible through the schema
            library_name = context.inspection_result.schema.name
            logger.info("Successfully loaded metadata for library %s", library_name)
        else:
            logger.warning("Failed to load metadata for library %s", context.provenance.get_display_name())

        # Check if inspection result is disqualifying
        if not context.inspection_result.is_usable():
            logger.error(
                "Library %s inspection failed with disqualifying issues: %s",
                context.provenance.get_display_name(),
                [issue.message for issue in context.inspection_result.issues],
            )
            # For disqualifying results, we still transition to InspectedState but it will have no allowed transitions
            return InspectedState

        # Auto-transition to InspectedState
        return InspectedState


class InspectedState(State):
    """State where inspection is complete and we have metadata."""

    @staticmethod
    def get_allowed_transitions_for_context(context: LibraryLifecycleContext) -> set[StateType]:
        """Get context-specific allowed transitions."""
        # If inspection result is unusable, block all transitions
        if context.inspection_result and not context.inspection_result.is_usable():
            return set()
        return {EvaluatingState}

    @staticmethod
    async def on_enter(context: LibraryLifecycleContext) -> StateType | None:
        if context.inspection_result and context.inspection_result.issues:
            logger.warning(
                "Library %s inspection completed with problems: %s",
                context.provenance.get_display_name(),
                [issue.message for issue in context.inspection_result.issues],
            )
        else:
            logger.info("Library %s inspection completed successfully", context.provenance.get_display_name())

        return None  # Wait for explicit transition to EvaluatingState


class EvaluatingState(State):
    """State where we evaluate the library against current system state."""

    @staticmethod
    def get_allowed_transitions_for_context(context: LibraryLifecycleContext) -> set[StateType]:  # noqa: ARG004
        """Get context-specific allowed transitions."""
        return {EvaluatedState}

    @staticmethod
    async def on_enter(context: LibraryLifecycleContext) -> StateType | None:
        logger.info("Evaluating library %s", context.provenance.get_display_name())

        context.evaluation_result = context.provenance.evaluate(context)

        # Auto-transition to EvaluatedState
        return EvaluatedState


class EvaluatedState(State):
    """State where evaluation is complete."""

    @staticmethod
    def get_allowed_transitions_for_context(context: LibraryLifecycleContext) -> set[StateType]:  # noqa: ARG004
        """Get context-specific allowed transitions."""
        return {InstallingState}

    @staticmethod
    async def on_enter(context: LibraryLifecycleContext) -> StateType | None:
        evaluation_issues = context.get_evaluation_issues()
        if evaluation_issues:
            logger.warning(
                "Library %s evaluation completed with problems: %s",
                context.provenance.get_display_name(),
                [issue.message for issue in evaluation_issues],
            )
        else:
            logger.info("Library %s evaluation completed successfully", context.provenance.get_display_name())

        return None  # Wait for explicit transition to InstallingState


class InstallingState(State):
    """State where we install the library and its dependencies."""

    @staticmethod
    def get_allowed_transitions_for_context(context: LibraryLifecycleContext) -> set[StateType]:  # noqa: ARG004
        """Get context-specific allowed transitions."""
        return {InstalledState}

    @staticmethod
    async def on_enter(context: LibraryLifecycleContext) -> StateType | None:
        logger.info("Installing library %s", context.provenance.get_display_name())

        # Check if user has disabled this library
        if not context.get_effective_active_state():
            issues = [LifecycleIssue(message="Library disabled by user", severity=LibraryStatus.FLAWED)]
            context.installation_result = InstallationResult(installation_path="", venv_path="", issues=issues)
            logger.info("Library %s installation skipped - disabled by user", context.provenance.get_display_name())
            return InstalledState

        # Perform installation using delegation
        context.installation_result = await context.provenance.install(context)

        # Auto-transition to InstalledState
        return InstalledState


class InstalledState(State):
    """State where installation is complete."""

    @staticmethod
    def get_allowed_transitions_for_context(context: LibraryLifecycleContext) -> set[StateType]:  # noqa: ARG004
        """Get context-specific allowed transitions."""
        return {LoadingState}

    @staticmethod
    async def on_enter(context: LibraryLifecycleContext) -> StateType | None:
        installation_issues = context.get_installation_issues()
        if installation_issues:
            logger.warning(
                "Library %s installation completed with problems: %s",
                context.provenance.get_display_name(),
                [issue.message for issue in installation_issues],
            )
        else:
            logger.info("Library %s installation completed successfully", context.provenance.get_display_name())

        return None  # Wait for explicit transition to LoadingState


class LoadingState(State):
    """State where we load the library into the registry."""

    @staticmethod
    def get_allowed_transitions_for_context(context: LibraryLifecycleContext) -> set[StateType]:  # noqa: ARG004
        """Get context-specific allowed transitions."""
        return {LoadedState}

    @staticmethod
    async def on_enter(context: LibraryLifecycleContext) -> StateType | None:
        logger.info("Loading library %s", context.provenance.get_display_name())

        # Check if user has disabled this library
        if not context.get_effective_active_state():
            issues = [LifecycleIssue(message="Library disabled by user", severity=LibraryStatus.FLAWED)]
            context.library_loaded_result = LibraryLoadedResult(issues=issues)
            logger.info("Library %s loading skipped - disabled by user", context.provenance.get_display_name())
            return LoadedState

        # Load the library into the registry using delegation
        schema = context.get_library_schema()
        if schema is None:
            issues = [LifecycleIssue(message="No schema available for loading", severity=LibraryStatus.UNUSABLE)]
            context.library_loaded_result = LibraryLoadedResult(issues=issues)
            logger.error("Cannot load library %s - no schema available", context.provenance.get_display_name())
            return LoadedState

        context.library_loaded_result = context.provenance.load_library(context)

        logger.info("Successfully loaded library %s", context.provenance.get_display_name())

        # Auto-transition to LoadedState
        return LoadedState


class LoadedState(State):
    """Final state where the library is loaded and ready for use."""

    @staticmethod
    def get_allowed_transitions_for_context(context: LibraryLifecycleContext) -> set[StateType]:  # noqa: ARG004
        """Get context-specific allowed transitions."""
        return set()  # Terminal state

    @staticmethod
    async def on_enter(context: LibraryLifecycleContext) -> StateType | None:
        library_loaded_issues = context.get_library_loaded_issues()
        if library_loaded_issues:
            logger.warning(
                "Library %s loading completed with problems: %s",
                context.provenance.get_display_name(),
                [issue.message for issue in library_loaded_issues],
            )
        else:
            logger.info("Library %s is now loaded and ready for use", context.provenance.get_display_name())

        return None  # Terminal state


class LibraryLifecycleFSM(FSM[LibraryLifecycleContext]):
    """Finite state machine for managing library lifecycle."""

    def __init__(self, provenance: LibraryProvenance) -> None:
        context = LibraryLifecycleContext(provenance=provenance)
        super().__init__(context)

    async def start_lifecycle(self) -> None:
        """Start the library lifecycle from CandidateState."""
        if self._current_state is not None:
            raise InvalidStateTransitionError(self._current_state, CandidateState, "Lifecycle has already been started")
        await self.start(CandidateState)

    async def begin_inspection(self) -> None:
        """Explicitly transition from Candidate to Inspecting."""
        self._validate_state_transition(InspectingState)
        await self.transition_state(InspectingState)

    async def begin_evaluation(self) -> None:
        """Explicitly transition from Inspected to Evaluating."""
        self._validate_state_transition(EvaluatingState)
        await self.transition_state(EvaluatingState)

    async def begin_installation(self) -> None:
        """Explicitly transition from Evaluated to Installing."""
        self._validate_state_transition(InstallingState)
        await self.transition_state(InstallingState)

    async def begin_loading(self) -> None:
        """Explicitly transition from Installed to Loading."""
        self._validate_state_transition(LoadingState)
        await self.transition_state(LoadingState)

    def get_context(self) -> LibraryLifecycleContext:
        """Get the current context."""
        return self._context

    def is_loaded(self) -> bool:
        """Check if the library is in the loaded state."""
        return self._current_state is LoadedState

    def has_problems(self) -> bool:
        """Check if the library has any problems."""
        context = self._context
        return bool(
            context.get_inspection_issues()
            or context.get_evaluation_issues()
            or context.get_installation_issues()
            or context.get_library_loaded_issues()
        )

    def get_all_problems(self) -> list[str]:
        """Get all problems from all stages."""
        context = self._context
        all_problems = []
        all_problems.extend([issue.message for issue in context.get_inspection_issues()])
        all_problems.extend([issue.message for issue in context.get_evaluation_issues()])
        all_problems.extend([issue.message for issue in context.get_installation_issues()])
        all_problems.extend([issue.message for issue in context.get_library_loaded_issues()])
        return all_problems

    def _validate_state_transition(self, target_state: StateType) -> None:
        """Validate that we can transition to the target state using state-based rules.

        Args:
            target_state: The state we want to transition to
        """
        if self._current_state is None:
            raise InvalidStateTransitionError(
                self._current_state, target_state, "No current state - lifecycle not started"
            )

        # Check if target state is allowed from current state
        allowed_transitions = self._current_state.get_allowed_transitions_for_context(self._context)  # type: ignore[attr-defined]
        if target_state not in allowed_transitions:
            allowed_names = [state.__name__ for state in allowed_transitions]
            if not allowed_names:
                raise InvalidStateTransitionError(
                    self._current_state,
                    target_state,
                    f"No transitions allowed from {self._current_state.__name__} due to disqualifying inspection issues",
                )
            raise InvalidStateTransitionError(
                self._current_state,
                target_state,
                f"Cannot transition from {self._current_state.__name__} to {target_state.__name__}. "
                f"Allowed transitions: {allowed_names}",
            )

        # Special validation for LoadingState - requires installation result
        installation_result = self._context.installation_result
        if target_state is LoadingState and not installation_result:
            raise InvalidStateTransitionError(
                self._current_state, target_state, "Installation result is required before loading"
            )

    def can_transition_to(self, target_state: StateType) -> bool:
        """Check if we can transition to the target state."""
        try:
            self._validate_state_transition(target_state)
        except InvalidStateTransitionError:
            return False
        else:
            return True

    def can_begin_inspection(self) -> bool:
        """Check if we can begin inspection."""
        return self.can_transition_to(InspectingState)

    def can_begin_evaluation(self) -> bool:
        """Check if we can begin evaluation."""
        return self.can_transition_to(EvaluatingState)

    def can_begin_installation(self) -> bool:
        """Check if we can begin installation."""
        return self.can_transition_to(InstallingState)

    def can_begin_loading(self) -> bool:
        """Check if we can begin loading."""
        return self.can_transition_to(LoadingState)

    def get_current_state_name(self) -> str:
        """Get the name of the current state."""
        return self._current_state.__name__ if self._current_state else "None"

    def get_allowed_transitions(self) -> set[StateType]:
        """Get the set of states that can be transitioned to from the current state."""
        if self._current_state is None:
            return set()

        return self._current_state.get_allowed_transitions_for_context(self._context)  # type: ignore[attr-defined]
