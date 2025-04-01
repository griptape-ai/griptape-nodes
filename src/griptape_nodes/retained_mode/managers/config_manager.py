import json
import os
from pathlib import Path
from typing import Any

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.config_events import (
    GetConfigCategoryRequest,
    GetConfigCategoryResultFailure,
    GetConfigCategoryResultSuccess,
    GetConfigValueRequest,
    GetConfigValueResultFailure,
    GetConfigValueResultSuccess,
    SetConfigCategoryRequest,
    SetConfigCategoryResultFailure,
    SetConfigCategoryResultSuccess,
    SetConfigValueRequest,
    SetConfigValueResultFailure,
    SetConfigValueResultSuccess,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.utils.dict_utils import get_dot_value, merge_dicts, set_dot_value

from .settings import ScriptSettingsDetail, Settings


class ConfigManager:
    """A class to manage application configuration and file pathing.

    This class handles loading and saving configuration from a config.json file
    located in the project root. If the config file is not found, it will create
    one with default values.

    Supports categorized configuration using dot notation (e.g., 'category.subcategory.key')
    to organize related configuration items.
    """

    def __init__(self, event_manager: EventManager | None = None, config_dir: str | None = None) -> None:
        """Initialize the ConfigManager.

        Args:
            event_manager: The EventManager instance to use for event handling.
            config_dir: Optional path to the config dir. If not provided,
                         it will use the current working directory.
        """
        self.config_dir = Path(config_dir) if config_dir else Path.home() / "GriptapeNodes/"
        self.user_config_path: Path = self.config_dir / "griptape_nodes_config.json"
        self.user_config: dict[str, Any] = {}

        self.user_config = Settings().model_dump()

        if event_manager is not None:
            # Register all our listeners.
            event_manager.assign_manager_to_request_type(
                GetConfigCategoryRequest, self.on_handle_get_config_category_request
            )
            event_manager.assign_manager_to_request_type(
                SetConfigCategoryRequest, self.on_handle_set_config_category_request
            )
            event_manager.assign_manager_to_request_type(GetConfigValueRequest, self.on_handle_get_config_value_request)
            event_manager.assign_manager_to_request_type(SetConfigValueRequest, self.on_handle_set_config_value_request)

    @property
    def workspace_path(self) -> Path:
        """Get the base file path from the configuration.

        Returns:
            Path object representing the base file path.
        """
        return Path(self.user_config.get("workspace_directory", str(Path.home())))

    @workspace_path.setter
    def workspace_path(self, path: str) -> None:
        """Set the base file path in the configuration.

        Args:
            path: The path to set as the base file path.
        """
        self.set_config_value("workspace_directory", str(Path(path).resolve()))

    def save_user_script_json(self, script_file_name: str) -> None:
        script_details = ScriptSettingsDetail(file_name=script_file_name, is_griptape_provided=False)
        config_loc = "app_events.on_app_initialization_complete.scripts_to_register"
        existing_scripts = self.get_config_value(config_loc)
        if not existing_scripts:
            existing_scripts = []
        existing_scripts.append(script_details.__dict__)
        self.set_config_value(config_loc, existing_scripts)

    def delete_user_script(self, script: dict) -> None:
        default_scripts = self.get_config_value("app_events.on_app_initialization_complete.scripts_to_register")
        default_scripts = [saved_script for saved_script in default_scripts if saved_script != script]
        self.set_config_value("app_events.on_app_initialization_complete.scripts_to_register", default_scripts)

    def get_full_path(self, relative_path: str) -> Path:
        """Get a full path by combining the base path with a relative path.

        Args:
            relative_path: A path relative to the base path.

        Returns:
            Path object representing the full path.
        """
        workspace_path = self.workspace_path
        return workspace_path / relative_path

    def get_config_value(self, key: str) -> Any:
        """Get a value from the configuration.

        If the value starts with a $, it will be pulled from the environment variables.

        Args:
            key: The configuration key to get. Can use dot notation for nested keys (e.g., 'category.subcategory.key').
                 If the key refers to a category (dictionary), returns the entire category.

        Returns:
            The value associated with the key, or the entire category if key points to a dict.
        """
        value = get_dot_value(self.user_config, key)

        if isinstance(value, str) and value.startswith("$"):
            value = os.getenv(value[1:], value)
        return value

    def set_config_value(self, key: str, value: Any) -> None:
        """Set a value in the configuration.

        Args:
            key: The configuration key to set. Can use dot notation for nested keys (e.g., 'category.subcategory.key').
            value: The value to associate with the key.
        """
        # Environment variables we handle separately.
        delta = set_dot_value({}, key, value)
        self.user_config = merge_dicts(self.user_config, delta)

        if not self.user_config_path.exists():
            self.user_config_path.touch()
            self.user_config_path.write_text(json.dumps({}, indent=2))

        # Merge in the delta with the current config.
        current_config = json.loads(self.user_config_path.read_text())
        self.user_config_path.write_text(json.dumps(merge_dicts(current_config, delta), indent=2))

    def on_handle_get_config_category_request(self, request: GetConfigCategoryRequest) -> ResultPayload:
        if request.category is None or request.category == "":
            # Return the whole shebang. Start with the defaults and then layer on the user config.
            contents = self.user_config
            details = "Successfully returned the entire config dictionary."
            print(details)  # TODO(griptape): Move to Log
            return GetConfigCategoryResultSuccess(contents=contents)

        # See if we got something valid.
        find_results = self.get_config_value(request.category)
        if find_results is None:
            details = f"Attempted to get config details for category '{request.category}'. Failed because no such category could be found."
            print(details)  # TODO(griptape): Move to Log
            return GetConfigCategoryResultFailure()

        if not isinstance(find_results, dict):
            details = f"Attempted to get config details for category '{request.category}'. Failed because this was was not a dictionary."
            print(details)  # TODO(griptape): Move to Log
            return GetConfigCategoryResultFailure()

        details = f"Successfully returned the config dictionary for section '{request.category}'."
        print(details)  # TODO(griptape): Move to Log
        return GetConfigCategoryResultSuccess(contents=find_results)

    def on_handle_set_config_category_request(self, request: SetConfigCategoryRequest) -> ResultPayload:
        # Validate the value is a dict
        if not isinstance(request.contents, dict):
            details = f"Attempted to set config details for category '{request.category}'. Failed because the contents provided were not a dictionary."
            print(details)  # TODO(griptape): Move to Log
            return SetConfigCategoryResultFailure()

        if request.category is None or request.category == "":
            # Assign the whole shebang.
            self.user_config = request.contents
            details = "Successfully assigned the entire config dictionary."
            print(details)  # TODO(griptape): Move to Log
            return SetConfigCategoryResultSuccess()

        self.set_config_value(key=request.category, value=request.contents)
        details = f"Successfully assigned the config dictionary for section '{request.category}'."
        print(details)  # TODO(griptape): Move to Log
        return SetConfigCategoryResultSuccess()

    def on_handle_get_config_value_request(self, request: GetConfigValueRequest) -> ResultPayload:
        if request.category_and_key == "":
            details = "Attempted to get config value but no category or key was specified."
            print(details)  # TODO(griptape): Move to Log
            return GetConfigValueResultFailure()

        # See if we got something valid.
        find_results = self.get_config_value(request.category_and_key)
        if find_results is None:
            details = f"Attempted to get config value for category.key '{request.category_and_key}'. Failed because no such category.key could be found."
            print(details)  # TODO(griptape): Move to Log
            return GetConfigValueResultFailure()

        details = f"Successfully returned the config value for section '{request.category_and_key}'."
        print(details)  # TODO(griptape): Move to Log
        return GetConfigValueResultSuccess(value=find_results)

    def on_handle_set_config_value_request(self, request: SetConfigValueRequest) -> ResultPayload:
        if request.category_and_key == "":
            details = "Attempted to set config value but no category or key was specified."
            print(details)  # TODO(griptape): Move to Log
            return SetConfigValueResultFailure()

        self.set_config_value(key=request.category_and_key, value=request.value)
        details = f"Successfully assigned the config value for category.key '{request.category_and_key}'."
        print(details)  # TODO(griptape): Move to Log
        return SetConfigValueResultSuccess()
