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
        """Private class for workflow construction."""

    _workflows: ClassVar[dict[str, Workflow]] = {}
    _registry_key: _RegistryKey = _RegistryKey()

    # Create a new workflow with everything we'd need
    @classmethod
    def generate_new_workflow(cls, file_path: str, metadata: WorkflowMetadata) -> Workflow:
        instance = cls()
        if metadata.name in instance._workflows:
            msg = f"Workflow with name '{metadata.name}' already registered."
            raise KeyError(msg)
        workflow = Workflow(registry_key=instance._registry_key, file_path=file_path, metadata=metadata)
        instance._workflows[metadata.name] = workflow
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
        instance = cls()
        return name in instance._workflows

    @classmethod
    def list_workflows(cls) -> dict[str, dict]:
        instance = cls()
        return {key: instance._workflows[key].get_workflow_metadata() for key in instance._workflows}

    @classmethod
    def get_complete_file_path(cls, relative_file_path: str) -> str:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        config_mgr = GriptapeNodes.ConfigManager()
        workspace_path = config_mgr.workspace_path
        complete_file_path = workspace_path / relative_file_path
        return str(complete_file_path)

    @classmethod
    def delete_workflow_by_name(cls, name: str) -> Workflow:
        instance = cls()
        if name not in instance._workflows:
            msg = f"Failed to delete Workflow. Workflow with name '{name}' has not been registered."
            raise KeyError(msg)
        return instance._workflows.pop(name)

    @classmethod
    def get_branches_of_workflow(cls, workflow_name: str) -> list[str]:
        """Get all workflows that are branches of the specified workflow."""
        instance = cls()
        branches = []
        for name, workflow in instance._workflows.items():
            if workflow.metadata.branched_from == workflow_name:
                branches.append(name)
        return branches


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
