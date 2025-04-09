from __future__ import annotations

from pathlib import Path
from typing import ClassVar, NamedTuple

from griptape.mixins.singleton_mixin import SingletonMixin
from pydantic import BaseModel


class LibraryNameAndVersion(NamedTuple):
    library_name: str
    library_version: str


class ScriptMetadata(BaseModel):
    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.1.0"

    name: str
    schema_version: str
    engine_version_created_with: str
    node_libraries_referenced: list[LibraryNameAndVersion]
    description: str | None = None
    image: str | None = None


class ScriptRegistry(SingletonMixin):
    class _RegistryKey:
        """Private class for script construction."""

    _scripts: dict[str, Script]
    _registry_key: _RegistryKey = _RegistryKey()

    def __init__(self) -> None:
        super().__init__()
        self._scripts = {}

    # Create a new script with everything we'd need
    @classmethod
    def generate_new_script(cls, file_path: str, metadata: ScriptMetadata) -> Script:
        instance = cls()
        if metadata.name in instance._scripts:
            msg = f"Script with name {metadata.name} already registered."
            raise KeyError(msg)
        script = Script(registry_key=instance._registry_key, file_path=file_path, metadata=metadata)
        instance._scripts[metadata.name] = script
        return script

    @classmethod
    def get_script_by_name(cls, name: str) -> Script:
        instance = cls()
        if name not in instance._scripts:
            msg = f"Failed to get Script. Script with name '{name}' has not been registered."
            raise KeyError(msg)
        return instance._scripts[name]

    @classmethod
    def list_scripts(cls) -> dict[str, dict]:
        instance = cls()
        return {key: instance._scripts[key].get_script_metadata() for key in instance._scripts}

    @classmethod
    def get_complete_file_path(cls, relative_file_path: str) -> str:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        config_mgr = GriptapeNodes().get_instance().ConfigManager()
        workspace_path = config_mgr.workspace_path
        complete_file_path = workspace_path / relative_file_path
        return str(complete_file_path)

    @classmethod
    def delete_script_by_name(cls, name: str) -> Script:
        instance = cls()
        if name not in instance._scripts:
            msg = f"Failed to delete Script. Script with name '{name}' has not been registered."
            raise KeyError(msg)
        return instance._scripts.pop(name)


class Script:
    """A script card to be ran."""

    metadata: ScriptMetadata
    file_path: str

    def __init__(self, registry_key: ScriptRegistry._RegistryKey, metadata: ScriptMetadata, file_path: str) -> None:
        if not isinstance(registry_key, ScriptRegistry._RegistryKey):
            msg = "Scripts can only be created through ScriptRegistry"
            raise TypeError(msg)

        self.metadata = metadata
        self.file_path = file_path

        # Get the absolute file path.
        complete_path = ScriptRegistry.get_complete_file_path(relative_file_path=file_path)
        if not Path(complete_path).is_file():
            msg = f"File path '{complete_path}' does not exist."
            raise ValueError(msg)

    def get_script_metadata(self) -> dict:
        # TODO(griptape): either convert the Pydantic schema to a dict or use it directly.
        return {
            "name": self.metadata.name,
            "file_path": self.file_path,
            "description": self.metadata.description,
            "image": self.metadata.image,
            "engine_version_created_with": self.metadata.engine_version_created_with,
            "node_libraries_referenced": self.metadata.node_libraries_referenced,
        }
