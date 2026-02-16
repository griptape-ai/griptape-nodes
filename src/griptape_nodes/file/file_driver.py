"""File driver interface for reading files from various sources.

This module re-exports the file driver components for backwards compatibility.
"""

from griptape_nodes.file.base_file_driver import BaseFileDriver
from griptape_nodes.file.file_driver_registry import (
    FileDriverNotFoundError,
    FileDriverRegistry,
)

# Backwards compatibility alias
FileDriver = BaseFileDriver

__all__ = [
    "BaseFileDriver",
    "FileDriver",
    "FileDriverNotFoundError",
    "FileDriverRegistry",
]
