import logging
import re
from os import getenv
from pathlib import Path

from dotenv import dotenv_values, get_key, load_dotenv, set_key, unset_key
from dotenv.main import DotEnv
from xdg_base_dirs import xdg_config_home

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

logger = logging.getLogger("griptape_nodes")

ENV_VAR_PATH = xdg_config_home() / "griptape_nodes" / ".env"


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
    def workspace_env_path(self) -> Path:
        return self.config_manager.workspace_path / ".env"

    def on_handle_get_secret_request(self, request: GetSecretValueRequest) -> ResultPayload:
        secret_key = SecretsManager._apply_secret_name_compliance(request.key)
        secret_value = self.get_secret(secret_key)

        if secret_value is None:
            details = f"Secret '{secret_key}' not found."
            logger.error(details)
            return GetSecretValueResultFailure()

        return GetSecretValueResultSuccess(value=secret_value)

    def on_handle_set_secret_request(self, request: SetSecretValueRequest) -> ResultPayload:
        secret_name = SecretsManager._apply_secret_name_compliance(request.key)
        secret_value = request.value

        # We don't want to echo the secret value back to the user, but we can at least tell them it changed.
        old_value = self.get_secret(secret_name, should_error_on_not_found=False)
        if old_value == secret_value:
            logger.info("Attempted to update secret '%s' but no change detected.", secret_name)
        elif old_value:
            logger.info("Secret '%s' changed.", secret_name)
        else:
            logger.info("Created secret '%s'", secret_name)

        self.set_secret(secret_name, secret_value)

        return SetSecretValueResultSuccess()

    def on_handle_get_all_secret_values_request(self, request: GetAllSecretValuesRequest) -> ResultPayload:  # noqa: ARG002
        secret_values = dotenv_values(ENV_VAR_PATH)

        return GetAllSecretValuesResultSuccess(values=secret_values)

    def on_handle_delete_secret_value_request(self, request: DeleteSecretValueRequest) -> ResultPayload:
        secret_name = SecretsManager._apply_secret_name_compliance(request.key)

        if not ENV_VAR_PATH.exists():
            details = f"Secret file does not exist: '{ENV_VAR_PATH}'"
            logger.error(details)
            return DeleteSecretValueResultFailure()

        if get_key(ENV_VAR_PATH, secret_name) is None:
            details = f"Secret {secret_name} not found in {ENV_VAR_PATH}"
            logger.error(details)
            return DeleteSecretValueResultFailure()

        unset_key(ENV_VAR_PATH, secret_name)

        logger.info("Secret '%s' deleted.", secret_name)

        return DeleteSecretValueResultSuccess()

    def get_secret(self, secret_name: str, *, should_error_on_not_found: bool = True) -> str | None:
        """Return the secret value, searching workspace env, global env, then OS env."""
        secret_name = SecretsManager._apply_secret_name_compliance(secret_name)

        search_order = [
            (str(self.workspace_env_path), lambda: DotEnv(self.workspace_env_path).get(secret_name)),
            (str(ENV_VAR_PATH), lambda: DotEnv(ENV_VAR_PATH).get(secret_name)),
            ("environment variables", lambda: getenv(secret_name)),
        ]

        value = None
        for source, fetch in search_order:
            value = fetch()
            if value is not None:
                logger.debug("Secret '%s' found in '%s'", secret_name, source)
                return value
            logger.debug("Secret '%s' not found in '%s'", secret_name, source)

        if should_error_on_not_found:
            logger.error("Secret '%s' not found", secret_name)
        return value

    def set_secret(self, secret_name: str, secret_value: str) -> None:
        if not ENV_VAR_PATH.exists():
            ENV_VAR_PATH.touch()
        set_key(ENV_VAR_PATH, secret_name, secret_value)
        load_dotenv(ENV_VAR_PATH, override=True)

    @staticmethod
    def _apply_secret_name_compliance(secret_name: str) -> str:
        # Ensure the string is in uppercase
        string = secret_name.upper()

        # Replace any spaces or invalid characters with underscores
        string = re.sub(r"\W+", "_", string)

        # Ensure it doesn't start with a number by prefixing an underscore if necessary
        if string and string[0].isdigit():
            string = "_" + string

        return string
