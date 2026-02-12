"""File read driver interface for reading files from various sources.

This module re-exports the file read driver components for backwards compatibility.
"""

from griptape_nodes.file.base_file_read_driver import BaseFileReadDriver
from griptape_nodes.file.file_read_driver_registry import (
    FileReadDriverNotFoundError,
    FileReadDriverRegistry,
)

# Backwards compatibility alias
FileReadDriver = BaseFileReadDriver

__all__ = [
    "BaseFileReadDriver",
    "FileReadDriver",
    "FileReadDriverNotFoundError",
    "FileReadDriverRegistry",
]
