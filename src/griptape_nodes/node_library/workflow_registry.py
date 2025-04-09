from __future__ import annotations

from pathlib import Path
from typing import ClassVar, NamedTuple

from griptape.mixins.singleton_mixin import SingletonMixin
from pydantic import BaseModel


class LibraryNameAndVersion(NamedTuple):
    library_name: str
    library_version: str


class WorkflowMetadata(BaseModel):
    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.1.0"

    name: str
    schema_version: str
    engine_version_created_with: str
    node_libraries_referenced: list[LibraryNameAndVersion]
    description: str | None = None
    image: str | None = None


class WorkflowRegistry(SingletonMixin):
    class _RegistryKey:
        """Private class for workflow construction."""

    _workflows: dict[str, Workflow]
    _registry_key: _RegistryKey = _RegistryKey()

    # Create a new workflow with everything we'd need
    @classmethod
    def generate_new_workflow(cls, file_path: str, metadata: WorkflowMetadata) -> Workflow:
        instance = cls()
        if metadata.name in instance._workflows:
            msg = f"Workflow with name {metadata.name} already registered."
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
    def list_workflows(cls) -> dict[str, dict]:
        instance = cls()
        return {key: instance._workflows[key].get_workflow_metadata() for key in instance._workflows}

    @classmethod
    def get_complete_file_path(cls, relative_file_path: str) -> str:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        config_mgr = GriptapeNodes().get_instance().ConfigManager()
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

    def get_workflow_metadata(self) -> dict:
        # TODO(griptape): either convert the Pydantic schema to a dict or use it directly.
        return {
            "name": self.metadata.name,
            "file_path": self.file_path,
            "description": self.metadata.description,
            "image": self.metadata.image,
            "engine_version_created_with": self.metadata.engine_version_created_with,
            "node_libraries_referenced": self.metadata.node_libraries_referenced,
        }
