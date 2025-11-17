"""Thread storage backend enumeration."""

from enum import StrEnum


class ThreadStorageBackend(StrEnum):
    """Enumeration of available thread storage backends."""

    LOCAL = "local"
    GTC = "gtc"
