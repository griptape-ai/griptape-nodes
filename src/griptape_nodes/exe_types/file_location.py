"""FileLocation class for encapsulating file paths with save policies."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@dataclass(frozen=True)
class FileLocation:
    """Encapsulates a file path with save policies.

    Attributes:
        resolved_path: Absolute path where file should be saved
        existing_file_policy: How to handle existing files (OVERWRITE, CREATE_NEW, FAIL)
        create_parent_dirs: Whether to create intermediate directories
    """

    resolved_path: str
    existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE
    create_parent_dirs: bool = True

    def save(
        self,
        data: bytes,
        *,
        use_direct_save: bool = True,
        skip_metadata_injection: bool = False,
    ) -> str:
        """Save data to the resolved path using configured policies.

        Args:
            data: Binary data to save
            use_direct_save: Whether to save directly without cloud storage
            skip_metadata_injection: Whether to skip metadata injection

        Returns:
            URL of the saved file for UI display

        Raises:
            FileExistsError: If file exists and policy is FAIL
            RuntimeError: If save operation fails
            ValueError: If path is invalid
        """
        path = Path(self.resolved_path)
        file_name = path.name

        return GriptapeNodes.StaticFilesManager().save_static_file(
            data=data,
            file_name=file_name,
            existing_file_policy=self.existing_file_policy,
            use_direct_save=use_direct_save,
            skip_metadata_injection=skip_metadata_injection,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize FileLocation for workflow save.

        Returns:
            Dictionary with resolved_path, existing_file_policy, create_parent_dirs
        """
        return {
            "resolved_path": self.resolved_path,
            "existing_file_policy": self.existing_file_policy.value,
            "create_parent_dirs": self.create_parent_dirs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileLocation":
        """Deserialize FileLocation from workflow load.

        Args:
            data: Dictionary with serialized FileLocation data

        Returns:
            FileLocation instance
        """
        return cls(
            resolved_path=data["resolved_path"],
            existing_file_policy=ExistingFilePolicy(data["existing_file_policy"]),
            create_parent_dirs=data.get("create_parent_dirs", True),
        )

    def __str__(self) -> str:
        """Return resolved path for string conversion."""
        return self.resolved_path
