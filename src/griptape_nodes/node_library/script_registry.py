from __future__ import annotations

from pathlib import Path

from griptape.mixins.singleton_mixin import SingletonMixin


class ScriptRegistry(SingletonMixin):
    class _RegistryKey:
        """Private class for script construction."""

    _scripts: dict[str, Script] = {}
    _registry_key: _RegistryKey = _RegistryKey()

    # Create a new script with everything we'd need
    @classmethod
    def generate_new_script(
        cls,
        name: str,
        relative_file_path: str,
        description: str | None = None,
        image: str | None = None,
    ) -> Script:
        instance = cls()
        if name in instance._scripts:
            # TODO(griptape): Should we rename scripts here?
            msg = f"Script with name {name} already registered."
            raise KeyError(msg)
        script = Script(name, relative_file_path, instance._registry_key, description, image)
        instance._scripts[name] = script
        return script

    @classmethod
    def get_script_by_name(cls, name: str) -> Script:
        instance = cls()
        if name not in instance._scripts:
            msg = f"Script with name {name} has not been registered."
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
            msg = f"Script with name {name} has not been registered."
            raise KeyError(msg)
        return instance._scripts.pop(name)


class Script:
    """A script card to be ran."""

    name: str
    relative_file_path: str
    description: str | None
    image: str | None  # TODO(griptape): Make work with real images

    def __init__(
        self,
        name: str,
        relative_file_path: str,
        registry_key: ScriptRegistry._RegistryKey,
        description: str | None = None,
        image: str | None = None,
    ) -> None:
        if not isinstance(registry_key, ScriptRegistry._RegistryKey):
            msg = "Scripts can only be created through ScriptRegistry"
            raise TypeError(msg)

        # Get the absolute file path.
        complete_path = ScriptRegistry.get_complete_file_path(relative_file_path=relative_file_path)
        if not Path(complete_path).is_file():
            msg = f"File path '{complete_path}' does not exist."
            raise ValueError(msg)
        self.name = name
        self.relative_file_path = relative_file_path
        self.description = description
        self.image = image

    def get_script_metadata(self) -> dict:
        return {
            "name": self.name,
            "file_path": self.relative_file_path,
            "description": self.description,
            "image": self.image,
        }
