"""Storage backend enumeration."""

from enum import StrEnum


class StorageBackend(StrEnum):
    """Enumeration of available storage backends."""

    LOCAL = "local"
    GTC = "gtc"
