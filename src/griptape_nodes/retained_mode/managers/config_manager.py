import json
import logging
from pathlib import Path
from typing import Any

from pydantic_settings import SettingsConfigDict
from xdg_base_dirs import xdg_config_home

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
from griptape_nodes.retained_mode.managers.settings import Settings, WorkflowSettingsDetail
from griptape_nodes.utils.dict_utils import get_dot_value, merge_dicts, set_dot_value

logger = logging.getLogger("griptape_nodes")

CONFIG_DIR = xdg_config_home() / "griptape_nodes"


class ConfigManager:
    """A class to manage application configuration and file pathing.

    This class handles loading and saving configuration from a config.json file
    located in the project root. If the config file is not found, it will create
    one with default values.

    Supports categorized configuration using dot notation (e.g., 'category.subcategory.key')
    to organize related configuration items.
    """

    def __init__(self, event_manager: EventManager | None = None) -> None:
        """Initialize the ConfigManager.

        Args:
            event_manager: The EventManager instance to use for event handling.
        """
        self.load_user_config()

        self._set_log_level(self.user_config.get("log_level", logging.INFO))

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
        return Path(self._workspace_path).resolve()

    @workspace_path.setter
    def workspace_path(self, path: str | Path) -> None:
        """Set the base file path in the configuration.

        Args:
            path: The path to set as the base file path.
        """
        self._workspace_path = str(Path(path).resolve())

    @property
    def user_config_path(self) -> Path:
        """Get the path to the user config file.

        Returns:
            Path object representing the user config file.
        """
        return self.workspace_path / "griptape_nodes_config.json"

    @property
    def config_files(self) -> list[Path]:
        """Get a list of config files to check for.

        Returns:
            List of Path objects representing the config files.
        """
        possible_config_files = [
            *self._find_config_files("griptape_nodes_config.json"),
            self.workspace_path / "griptape_nodes_config.json",
            *self._find_config_files("griptape_nodes_config.toml"),
            self.workspace_path / "griptape_nodes_config.toml",
            *self._find_config_files("griptape_nodes_config.yaml"),
            self.workspace_path / "griptape_nodes_config.yaml",
        ]

        return [config_file for config_file in possible_config_files if config_file.exists()]

    def load_user_config(self) -> None:
        """Load user configuration from the config file."""
        # We need to load the fully merged config once so that
        # we can get the workspace directory which will inform where to get more config files.
        # Workspace directory should probably be decoupled from the config file.
        # TODO(collin): https://github.com/griptape-ai/griptape-nodes/issues/424
        Settings.model_config = SettingsConfigDict(
            json_file=self._find_config_files("griptape_nodes_config.json"),
            toml_file=self._find_config_files("griptape_nodes_config.toml"),
            yaml_file=self._find_config_files("griptape_nodes_config.yaml"),
            extra="allow",
        )
        settings = Settings()
        workspace_path = Path(settings.workspace_directory).resolve()

        # Now we load the config again, this time considering the workspace directory.
        Settings.model_config = SettingsConfigDict(
            json_file=[
                *self._find_config_files("griptape_nodes_config.json"),
                workspace_path / "griptape_nodes_config.json",
            ],
            toml_file=[
                *self._find_config_files("griptape_nodes_config.toml"),
                workspace_path / "griptape_nodes_config.toml",
            ],
            yaml_file=[
                *self._find_config_files("griptape_nodes_config.yaml"),
                workspace_path / "griptape_nodes_config.yaml",
            ],
            extra="allow",
        )
        settings = Settings()
        self.user_config = settings.model_dump()
        self.workspace_path = settings.workspace_directory

    def save_user_workflow_json(self, workflow_file_name: str) -> None:
        workflow_details = WorkflowSettingsDetail(file_name=workflow_file_name, is_griptape_provided=False)
        config_loc = "app_events.on_app_initialization_complete.workflows_to_register"
        existing_workflows = self.get_config_value(config_loc)
        if not existing_workflows:
            existing_workflows = []
        existing_workflows.append(workflow_details.__dict__)
        self.set_config_value(config_loc, existing_workflows)

    def delete_user_workflow(self, workflow: dict) -> None:
        default_workflows = self.get_config_value("app_events.on_app_initialization_complete.workflows_to_register")
        if default_workflows:
            default_workflows = [
                saved_workflow
                for saved_workflow in default_workflows
                if saved_workflow["file_name"] != workflow["file_path"]
            ]
            self.set_config_value("app_events.on_app_initialization_complete.workflows_to_register", default_workflows)

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
        if value is None:
            msg = f"Config key '{key}' not found in config file."
            logger.error(msg)
            return None

        if isinstance(value, str) and value.startswith("$"):
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            value = GriptapeNodes.SecretsManager().get_secret(value[1:], value)

        return value

    def set_config_value(self, key: str, value: Any) -> None:
        """Set a value in the configuration.

        Args:
            key: The configuration key to set. Can use dot notation for nested keys (e.g., 'category.subcategory.key').
            value: The value to associate with the key.
        """
        delta = set_dot_value({}, key, value)
        workspace_dir = self.workspace_path
        if key == "log_level":
            self._set_log_level(value)
        elif key == "workspace_directory":
            # If the key is workspace_directory, we want to write the value
            # to the home config directory (~/.config/griptape_nodes) and not the workspace directory.
            workspace_dir = CONFIG_DIR
            self.workspace_path = value
        self.user_config = merge_dicts(self.user_config, delta)
        self._write_user_config_delta(delta, workspace_dir)

        # If the key is workspace_directory, we need to fully reload the user config
        # because the workspace changing may influence the config files we load.
        if key == "workspace_directory":
            self.load_user_config()
        logger.debug("Config value '%s' set to '%s'", key, value)

    def on_handle_get_config_category_request(self, request: GetConfigCategoryRequest) -> ResultPayload:
        if request.category is None or request.category == "":
            # Return the whole shebang. Start with the defaults and then layer on the user config.
            contents = self.user_config
            details = "Successfully returned the entire config dictionary."
            logger.info(details)
            return GetConfigCategoryResultSuccess(contents=contents)

        # See if we got something valid.
        find_results = self.get_config_value(request.category)
        if find_results is None:
            details = f"Attempted to get config details for category '{request.category}'. Failed because no such category could be found."
            logger.error(details)
            return GetConfigCategoryResultFailure()

        if not isinstance(find_results, dict):
            details = f"Attempted to get config details for category '{request.category}'. Failed because this was was not a dictionary."
            logger.error(details)
            return GetConfigCategoryResultFailure()

        details = f"Successfully returned the config dictionary for section '{request.category}'."
        logger.info(details)
        return GetConfigCategoryResultSuccess(contents=find_results)

    def on_handle_set_config_category_request(self, request: SetConfigCategoryRequest) -> ResultPayload:
        # Validate the value is a dict
        if not isinstance(request.contents, dict):
            details = f"Attempted to set config details for category '{request.category}'. Failed because the contents provided were not a dictionary."
            logger.error(details)
            return SetConfigCategoryResultFailure()

        if request.category is None or request.category == "":
            # Assign the whole shebang.
            self._write_user_config_delta(request.contents, self.user_config_path)
            details = "Successfully assigned the entire config dictionary."
            logger.info(details)
            return SetConfigCategoryResultSuccess()

        self.set_config_value(key=request.category, value=request.contents)
        details = f"Successfully assigned the config dictionary for section '{request.category}'."
        logger.info(details)
        return SetConfigCategoryResultSuccess()

    def on_handle_get_config_value_request(self, request: GetConfigValueRequest) -> ResultPayload:
        if request.category_and_key == "":
            details = "Attempted to get config value but no category or key was specified."
            logger.error(details)
            return GetConfigValueResultFailure()

        # See if we got something valid.
        find_results = self.get_config_value(request.category_and_key)
        if find_results is None:
            details = f"Attempted to get config value for category.key '{request.category_and_key}'. Failed because no such category.key could be found."
            logger.error(details)
            return GetConfigValueResultFailure()

        details = f"Successfully returned the config value for section '{request.category_and_key}'."
        logger.info(details)
        return GetConfigValueResultSuccess(value=find_results)

    def on_handle_set_config_value_request(self, request: SetConfigValueRequest) -> ResultPayload:
        if request.category_and_key == "":
            details = "Attempted to set config value but no category or key was specified."
            logger.error(details)
            return SetConfigValueResultFailure()

        self.set_config_value(key=request.category_and_key, value=request.value)
        details = f"Successfully assigned the config value for category.key '{request.category_and_key}'."
        logger.info(details)
        return SetConfigValueResultSuccess()

    def _write_user_config_delta(self, user_config_delta: dict, workspace_dir: Path) -> None:
        """Write the user configuration to the config file.

        This method creates the config file if it doesn't exist and writes the
        current configuration to it.

        Args:
            user_config_delta: The user configuration delta to write to the file Will be merged with the existing config on disk.
            workspace_dir: The path to the config file
        """
        user_config_path = workspace_dir / "griptape_nodes_config.json"

        if not user_config_path.exists():
            user_config_path.parent.mkdir(parents=True, exist_ok=True)
            user_config_path.touch()
            user_config_path.write_text(json.dumps({}, indent=2))
        current_config = json.loads(user_config_path.read_text())
        merged_config = merge_dicts(current_config, user_config_delta)
        user_config_path.write_text(json.dumps(merged_config, indent=2))

    def _find_config_files(self, filename: str) -> list[Path]:
        """Find configuration files in the workspace directory and parent directories.

        Searches in the following priority order:
        1. XDG_CONFIG_HOME (e.g., `~/.config/griptape_nodes/griptape_nodes_config.json`)
        2. Current working directory
        3. Parent directories up to HOME
        """
        config_files = []

        # Search XDG_CONFIG_HOME (e.g., `~/.config/griptape_nodes/griptape_nodes_config.json`)
        config_files.append(xdg_config_home() / "griptape_nodes" / filename)

        # Recursively search parent directories up to HOME
        current_path = Path.cwd()
        while current_path not in (Path.home(), current_path.parent) and current_path != current_path.parent:
            config_files.append(current_path / filename)
            current_path = current_path.parent

        return config_files

    def _set_log_level(self, level: str) -> None:
        """Set the log level for the logger.

        Args:
            level: The log level to set (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
        """
        try:
            logger.setLevel(level.upper())
        except ValueError:
            logger.error("Invalid log level %s. Defaulting to INFO.", level)
            logger.setLevel(logging.INFO)
