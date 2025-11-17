from __future__ import annotations

import json
import logging
from datetime import datetime  # noqa: TC003 (can't put into type checking block as Pydantic model relies on it)
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

from pydantic import BaseModel, Field, field_serializer, field_validator

from griptape_nodes.node_library.library_registry import (
    LibraryNameAndVersion,  # noqa: TC001 (putting this into type checking causes it to not be defined)
)
from griptape_nodes.utils.metaclasses import SingletonMeta

logger = logging.getLogger("griptape_nodes")


class LibraryNameAndNodeType(NamedTuple):
    library_name: str
    node_type: str


# Type aliases for clarity
type NodeName = str
type ParameterName = str
type ParameterAttribute = str
type ParameterMinimalDict = dict[ParameterAttribute, Any]
type NodeParametersMapping = dict[NodeName, dict[ParameterName, ParameterMinimalDict]]


class WorkflowShape(BaseModel):
    """This structure reflects the input and output shapes extracted from StartNodes and EndNodes inside of the workflow.

    A workflow may have multiple StartNodes and multiple EndNodes, each contributing their parameters
    to the overall workflow shape.

    Structure is:
    - inputs: {start_node_name: {param_name: param_minimal_dict}}
    - outputs: {end_node_name: {param_name: param_minimal_dict}}
    """

    inputs: NodeParametersMapping = Field(default_factory=dict)
    outputs: NodeParametersMapping = Field(default_factory=dict)


class WorkflowMetadata(BaseModel):
    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.13.0"

    name: str
    schema_version: str
    engine_version_created_with: str
    node_libraries_referenced: list[LibraryNameAndVersion]
    node_types_used: set[LibraryNameAndNodeType] = Field(default_factory=set)
    workflows_referenced: list[str] | None = None
    description: str | None = None
    image: str | None = None
    is_griptape_provided: bool | None = False
    is_template: bool | None = False
    creation_date: datetime | None = Field(default=None)
    last_modified_date: datetime | None = Field(default=None)
    branched_from: str | None = Field(default=None)
    workflow_shape: WorkflowShape | None = Field(default=None)

    @field_serializer("node_types_used")
    def serialize_node_types_used(self, node_types_used: set[LibraryNameAndNodeType]) -> list[list[str]]:
        """Serialize node_types_used as list of tuples for TOML compatibility.

        Sets and NamedTuples are not directly supported by TOML, so we convert the set
        to a list of lists (each inner list represents [library_name, node_type]).
        """
        return [[nt.library_name, nt.node_type] for nt in sorted(node_types_used)]

    @field_validator("node_types_used", mode="before")
    @classmethod
    def validate_node_types_used(cls, value: Any) -> set[LibraryNameAndNodeType]:
        """Deserialize node_types_used from list of lists during TOML loading.

        When loading workflow metadata from TOML files, the node_types_used field
        is stored as a list of [library_name, node_type] pairs that needs to be
        converted back to a set of LibraryNameAndNodeType objects. This validator
        handles the expected input formats:
        - List of lists (from TOML deserialization)
        - Set of LibraryNameAndNodeType (from direct Python construction)
        - Empty list (for workflows with no nodes)
        """
        if isinstance(value, set):
            return value
        if isinstance(value, list):
            return {LibraryNameAndNodeType(library_name=item[0], node_type=item[1]) for item in value}
        msg = f"Expected list or set for node_types_used, got {type(value)}"
        raise ValueError(msg)

    @field_serializer("workflow_shape")
    def serialize_workflow_shape(self, workflow_shape: WorkflowShape | None) -> str | None:
        """Serialize WorkflowShape as JSON string to avoid TOML serialization issues.

        The WorkflowShape contains deeply nested dictionaries with None values that are
        meaningful data (e.g., default_value: None). TOML's nested table format creates
        unreadable output and tomlkit fails on None values in nested structures.
        JSON preserves None as null and keeps the data compact and readable.
        """
        if workflow_shape is None:
            return None
        # Use json.dumps to preserve None values as null, which TOML can handle
        return json.dumps(workflow_shape.model_dump(), separators=(",", ":"))

    @field_validator("workflow_shape", mode="before")
    @classmethod
    def validate_workflow_shape(cls, value: Any) -> WorkflowShape | None:
        """Deserialize WorkflowShape from JSON string during TOML loading.

        When loading workflow metadata from TOML files, the workflow_shape field
        is stored as a JSON string that needs to be converted back to a WorkflowShape
        object. This validator handles the expected input formats:
        - JSON strings (from TOML deserialization)
        - WorkflowShape objects (from direct Python construction)
        - None values (workflows without Start/End nodes)

        If JSON deserialization fails, logs a warning and returns None for graceful
        degradation, consistent with other metadata parsing failures in this codebase.
        """
        if value is None:
            return None
        if isinstance(value, WorkflowShape):
            return value
        if isinstance(value, str):
            try:
                data = json.loads(value)
                return WorkflowShape(**data)
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.error("Failed to deserialize workflow_shape from JSON: %s", e)
                return None
        # Unexpected type - let Pydantic's normal validation handle it
        return value


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

        # If the path is already absolute, return it as-is
        if Path(relative_file_path).is_absolute():
            return relative_file_path

        # Otherwise, resolve it relative to the workspace
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
