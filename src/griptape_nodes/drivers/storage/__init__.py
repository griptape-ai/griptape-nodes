"""Package for griptape nodes storage drivers.

Storage drivers are responsible for managing the storage and retrieval of files.
"""

from .storage_backend import StorageBackend

__all__ = ["StorageBackend"]
