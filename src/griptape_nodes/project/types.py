"""Types for project file operations."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ExistingFilePolicy(Enum):
    """Policy for handling existing files during save operations."""

    CREATE_NEW = "CREATE_NEW"  # Auto-increment index to find next available filename
    OVERWRITE = "OVERWRITE"  # Overwrite existing file
    FAIL = "FAIL"  # Raise error if file exists


@dataclass
class SaveRequest:
    """Request to save file using project configuration.

    Created by ProjectFileParameter - contains all config needed for saving.
    """

    data: bytes
    macro_template: str  # e.g., "{outputs}/{node_name}_{file_name_base}{_index?:03}.{file_extension}"
    variables: dict[str, str | int]  # All variables for macro resolution
    policy: ExistingFilePolicy  # CREATE_NEW, OVERWRITE, or FAIL
    create_dirs: bool  # Whether to create parent directories


@dataclass
class SaveResult:
    """Result of save operation."""

    path: Path  # Absolute path where file was saved
    url: str  # Display URL for UI (same as path for local files)
    index_used: int | None  # If _index was incremented, what value was used


@dataclass
class ProjectFileSaveConfig:
    """Configuration for file saving (output from ConfigureProjectFileSave node).

    This allows ConfigureProjectFileSave to output custom configuration that
    save nodes can use to override default situation settings.
    """

    macro_template: str
    policy: ExistingFilePolicy
    create_dirs: bool
