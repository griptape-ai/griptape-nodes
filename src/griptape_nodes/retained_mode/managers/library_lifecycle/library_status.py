"""Library lifecycle and fitness enumerations."""

from enum import StrEnum


class LibraryLifecycleState(StrEnum):
    """Lifecycle states for library loading."""

    FAILURE = "failure"
    DISCOVERED = "discovered"
    INSPECTED = "inspected"
    EVALUATED = "evaluated"
    DEPENDENCIES_INSTALLED = "dependencies_installed"
    LOADED = "loaded"


class LibraryFitness(StrEnum):
    """Fitness of the library that was attempted to be loaded."""

    GOOD = "GOOD"  # No errors detected during loading. Registered.
    FLAWED = "FLAWED"  # Some errors detected, but recoverable. Registered.
    UNUSABLE = "UNUSABLE"  # Errors detected and not recoverable. Not registered.
    MISSING = "MISSING"  # File not found. Not registered.
    NOT_EVALUATED = "NOT_EVALUATED"  # Library has not been evaluated yet.
