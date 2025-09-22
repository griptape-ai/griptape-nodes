from __future__ import annotations

from datetime import datetime  # noqa: TC003 (can't put into type checking block as Pydantic model relies on it)
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from griptape_nodes.node_library.library_registry import (
    LibraryNameAndVersion,  # noqa: TC001 (putting this into type checking causes it to not be defined)
)
from griptape_nodes.utils.metaclasses import SingletonMeta


class WorkflowMetadata(BaseModel):
    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.7.0"

    name: str
    schema_version: str
    engine_version_created_with: str
    node_libraries_referenced: list[LibraryNameAndVersion]
    workflows_referenced: list[str] | None = None
    description: str | None = None
    image: str | None = None
    is_griptape_provided: bool | None = False
    is_template: bool | None = False
    creation_date: datetime | None = Field(default=None)
    last_modified_date: datetime | None = Field(default=None)
    branched_from: str | None = Field(default=None)


class WorkflowRegistry(metaclass=SingletonMeta):
    class _RegistryKey:
        """Private class for workflow construction.

        Attributes:
            _workflows: A dictionary to hold registered workflows. Keys are file paths, values are Workflow instances.
            _registry_key: A unique key to control workflow instantiation.
        """

    _workflows: ClassVar[dict[str, Workflow]] = {}
    _registry_key: _RegistryKey = _RegistryKey()

    @classmethod
    def generate_new_workflow(cls, file_path: str, metadata: WorkflowMetadata) -> Workflow:
        instance = cls()
        if file_path in instance._workflows:
            msg = f"Workflow with file path '{file_path}' already registered."
            raise KeyError(msg)
        workflow = Workflow(registry_key=instance._registry_key, file_path=file_path, metadata=metadata)
        workflow_identifier = cls.get_workflow_identifier(file_path)
        instance._workflows[workflow_identifier] = workflow
        return workflow

    @classmethod
    def get_workflow_by_name(cls, name: str) -> Workflow:
        instance = cls()
        if name not in instance._workflows:
            msg = f"Failed to get Workflow. Workflow with name '{name}' has not been registered."
            raise KeyError(msg)
        return instance._workflows[name]

    @classmethod
    def has_workflow_with_name(cls, name: str) -> bool:
        """Check if workflow exists with the given name or path."""
        try:
            cls.get_workflow_by_name(name)
        except KeyError:
            return False
        else:
            return True

    @classmethod
    def list_workflows(cls) -> dict[str, dict]:
        """List all workflows, keyed by file path."""
        instance = cls()
        return {file_path: workflow.get_workflow_metadata() for file_path, workflow in instance._workflows.items()}

    @classmethod
    def get_complete_file_path(cls, relative_file_path: str) -> str:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # If the path is already absolute, return it as-is
        if Path(relative_file_path).is_absolute():
            return relative_file_path

        # Otherwise, resolve it relative to the workspace
        config_mgr = GriptapeNodes.ConfigManager()
        workspace_path = config_mgr.workspace_path
        complete_file_path = workspace_path / relative_file_path
        return str(complete_file_path)

    @classmethod
    def clean_workflow_name(cls, name: str) -> str:
        """Clean a workflow name to be a valid Python module name.

        Args:
            name: The raw workflow name

        Returns:
            Cleaned name (lowercase with underscores)
        """
        # Convert to lowercase and replace non-alphanumeric chars with underscores
        import re

        cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower())
        # Remove consecutive underscores
        cleaned = re.sub(r"_+", "_", cleaned)
        # Remove leading/trailing underscores
        cleaned = cleaned.strip("_")
        return cleaned if cleaned else "workflow"

    @classmethod
    def get_workflow_identifier(cls, file_path: str) -> str:
        """Get workflow identifier from file path.

        Args:
            file_path: File path (absolute or relative to workspace)

        Returns:
            Workflow identifier (path without extension)
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # If the path is already absolute, return it without extension
        if Path(file_path).is_absolute():
            return str(Path(file_path).with_suffix(""))

        config_mgr = GriptapeNodes.ConfigManager()
        if not Path(cls.get_complete_file_path(file_path)).is_relative_to(config_mgr.workspace_path):
            msg = (
                f"Relative file path '{file_path}' is not relative to the workspace path '{config_mgr.workspace_path}'."
            )
            raise ValueError(msg)

        return (
            Path(cls.get_complete_file_path(file_path))
            .relative_to(config_mgr.workspace_path)
            .with_suffix("")
            .as_posix()
        )

    @classmethod
    def delete_workflow_by_name(cls, name: str) -> Workflow:
        instance = cls()
        if name not in instance._workflows:
            msg = f"Failed to delete Workflow. Workflow with name '{name}' has not been registered."
            raise KeyError(msg)
        return instance._workflows.pop(name)

    @classmethod
    def update_workflow_identifier(cls, old_identifier: str, new_file_path: str) -> None:
        """Update a workflow's identifier in the registry after a move operation.

        Args:
            old_identifier: The current identifier (key) in the registry
            new_file_path: The new file path for the workflow

        Raises:
            KeyError: If the old identifier doesn't exist in the registry
        """
        instance = cls()
        if old_identifier not in instance._workflows:
            msg = f"Failed to update workflow identifier. Workflow with identifier '{old_identifier}' has not been registered."
            raise KeyError(msg)

        # Get the workflow and update its file path
        workflow = instance._workflows.pop(old_identifier)
        workflow.file_path = new_file_path

        # Re-register with the new identifier
        new_identifier = cls.get_workflow_identifier(new_file_path)
        instance._workflows[new_identifier] = workflow

    @classmethod
    def get_branches_of_workflow(cls, workflow_name: str) -> list[str]:
        """Get all workflows that are branches of the specified workflow."""
        instance = cls()
        return [
            workflow.metadata.name
            for workflow in instance._workflows.values()
            if workflow.metadata.branched_from == workflow_name
        ]


class Workflow:
    """A workflow card to be ran."""

    metadata: WorkflowMetadata
    file_path: str

    def __init__(self, registry_key: WorkflowRegistry._RegistryKey, metadata: WorkflowMetadata, file_path: str) -> None:
        if not isinstance(registry_key, WorkflowRegistry._RegistryKey):
            msg = "Workflows can only be created through WorkflowRegistry"
            raise TypeError(msg)

        self.metadata = metadata
        self.file_path = file_path

        # Get the absolute file path.
        complete_path = WorkflowRegistry.get_complete_file_path(relative_file_path=file_path)
        if not Path(complete_path).is_file():
            msg = f"File path '{complete_path}' does not exist."
            raise ValueError(msg)

    @property
    def is_synced(self) -> bool:
        """Check if this workflow is in the synced workflows directory."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        config_mgr = GriptapeNodes.ConfigManager()
        synced_directory = config_mgr.get_config_value("synced_workflows_directory")

        # Get the full path to the synced workflows directory
        synced_path = config_mgr.get_full_path(synced_directory)

        # Get the complete file path for this workflow
        complete_file_path = WorkflowRegistry.get_complete_file_path(self.file_path)

        # Check if the workflow file is within the synced directory
        return Path(complete_file_path).is_relative_to(synced_path)

    def get_workflow_metadata(self) -> dict:
        # Convert from the Pydantic schema.
        ret_val = {**self.metadata.model_dump()}

        # The schema doesn't have the file path in it, because it is baked into the file itself.
        # Customers of this function need that, so let's stuff it in.
        ret_val["file_path"] = self.file_path
        ret_val["is_synced"] = self.is_synced
        return ret_val
