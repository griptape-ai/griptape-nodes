"""Library status enumeration."""

from enum import StrEnum


class LibraryStatus(StrEnum):
    """Status of the library that was attempted to be loaded."""

    GOOD = "GOOD"  # No errors detected during loading. Registered.
    FLAWED = "FLAWED"  # Some errors detected, but recoverable. Registered.
    UNUSABLE = "UNUSABLE"  # Errors detected and not recoverable. Not registered.
    MISSING = "MISSING"  # File not found. Not registered.
