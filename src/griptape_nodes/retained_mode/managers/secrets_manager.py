from os import getenv
from pathlib import Path

from dotenv import dotenv_values, get_key, set_key, unset_key

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.secrets_events import (
    DeleteSecretValueRequest,
    DeleteSecretValueResultFailure,
    DeleteSecretValueResultSuccess,
    GetAllSecretValuesRequest,
    GetAllSecretValuesResultSuccess,
    GetSecretValueRequest,
    GetSecretValueResultFailure,
    GetSecretValueResultSuccess,
    SetSecretValueRequest,
    SetSecretValueResultSuccess,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager


class SecretsManager:
    def __init__(self, config_manager: ConfigManager, event_manager: EventManager | None = None) -> None:
        self.config_manager = config_manager

        # Register all our listeners.
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(GetSecretValueRequest, self.on_handle_get_secret_request)
            event_manager.assign_manager_to_request_type(SetSecretValueRequest, self.on_handle_set_secret_request)
            event_manager.assign_manager_to_request_type(
                GetAllSecretValuesRequest, self.on_handle_get_all_secret_values_request
            )
            event_manager.assign_manager_to_request_type(
                DeleteSecretValueRequest, self.on_handle_delete_secret_value_request
            )

    @property
    def env_var_path(self) -> Path:
        return self.config_manager.workspace_path / ".env"

    def on_handle_get_secret_request(self, request: GetSecretValueRequest) -> ResultPayload:
        secret_key = request.key
        secret_value = self.get_secret(secret_key)

        if secret_value is None:
            details = f"Secret {secret_key} not found: '{secret_key}'"
            print(details)  # TODO(griptape): Move to Log
            return GetSecretValueResultFailure()

        return GetSecretValueResultSuccess(value=secret_value)

    def on_handle_set_secret_request(self, request: SetSecretValueRequest) -> ResultPayload:
        secret_name = request.key
        secret_value = request.value

        self.set_secret(secret_name, secret_value)

        return SetSecretValueResultSuccess()

    def on_handle_get_all_secret_values_request(self, request: GetAllSecretValuesRequest) -> ResultPayload:  # noqa: ARG002
        secret_values = dotenv_values(self.env_var_path)

        return GetAllSecretValuesResultSuccess(values=secret_values)

    def on_handle_delete_secret_value_request(self, request: DeleteSecretValueRequest) -> ResultPayload:
        secret_name = request.key

        if not self.env_var_path.exists():
            details = f"Secret file does not exist: '{self.env_var_path}'"
            print(details)  # TODO(griptape): Move to Log
            return DeleteSecretValueResultFailure()

        if not get_key(self.env_var_path, secret_name):
            details = f"Secret {secret_name} not found in {self.env_var_path}"
            print(details)  # TODO(griptape): Move to Log
            return DeleteSecretValueResultFailure()

        unset_key(self.env_var_path, secret_name)

        return DeleteSecretValueResultSuccess()

    def get_secret(self, secret_name: str, default: str | None = None) -> str | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        value = get_key(self.env_var_path, secret_name)
        if value is None:
            GriptapeNodes.get_logger().warning(
                "Secret %s not found in %s, looking in environment variables", secret_name, self.env_var_path
            )
            # Check if the secret is set in the environment variables
            value = getenv(secret_name)
        if value is None:
            GriptapeNodes.get_logger().warning(
                "Secret %s not found in environment variables, using default value %s", secret_name, default
            )
            # Check if the secret is set in the config manager
            value = default
        return value

    def set_secret(self, secret_name: str, secret_value: str) -> None:
        if not self.env_var_path.exists():
            self.env_var_path.touch()
        set_key(self.env_var_path, secret_name, secret_value)
