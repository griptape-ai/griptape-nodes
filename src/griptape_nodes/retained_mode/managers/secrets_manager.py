import logging
import os
import re
from pathlib import Path
from typing import Literal, overload

from dotenv import dotenv_values, get_key, load_dotenv, set_key, unset_key
from dotenv.main import DotEnv
from xdg_base_dirs import xdg_config_home

from griptape_nodes.retained_mode.events.app_events import SecretChanged
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
from griptape_nodes.retained_mode.managers.settings import SECRETS_TO_REGISTER_KEY
from griptape_nodes.utils.dict_utils import normalize_secrets_to_register

logger = logging.getLogger("griptape_nodes")

ENV_VAR_PATH = xdg_config_home() / "griptape_nodes" / ".env"


class SecretsManager:
    def __init__(self, config_manager: ConfigManager, event_manager: EventManager | None = None) -> None:
        self.config_manager = config_manager
        self._event_manager = event_manager

        # Track which keys were sourced from .env files so refresh_from_env_file
        # can pop deleted keys back out of os.environ. Without this, a deleted
        # secret remains in os.environ as a stale shadow because load_dotenv
        # only assigns keys that are present in the file.
        self._loaded_env_keys: set[str] = set()

        # So that users can access secrets directly via `os.environ`
        load_dotenv(self.workspace_env_path, override=False)
        load_dotenv(ENV_VAR_PATH, override=False)
        if self.workspace_env_path.exists():
            self._loaded_env_keys.update(dotenv_values(self.workspace_env_path).keys())
        if ENV_VAR_PATH.exists():
            self._loaded_env_keys.update(dotenv_values(ENV_VAR_PATH).keys())

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

    def _notify_workers_to_refresh_secrets(self) -> None:
        """Tell every registered worker to re-read the shared .env from disk.

        Only the orchestrator's WorkerManager has any registered workers, so on
        a worker process this is a cheap no-op via ``schedule_broadcast``.
        Imported lazily because ``griptape_nodes.app`` is not importable at the
        module level here -- SecretsManager is loaded during engine boot,
        before ``app/__init__`` has finished importing.
        """
        from griptape_nodes.app.worker_routing import RefreshSecretsRequest, schedule_broadcast

        schedule_broadcast(RefreshSecretsRequest)

    def refresh_from_env_file(self) -> None:
        """Re-read the .env files into os.environ, applying the documented precedence.

        Same-machine workers share ~/.config/griptape_nodes/.env with the
        orchestrator, but each process captures the file contents into os.environ
        at boot. When the orchestrator updates the file, a worker's os.environ
        keeps the old value -- and get_secret() sees environment variables first,
        so it returns the stale value.

        Reload global first (lowest priority) and workspace second (higher
        priority) with override=True at each step. This matches the precedence
        documented on get_secret: workspace overrides global. Reversing the
        order would let global clobber workspace for keys present in both.

        Also drops keys that disappeared from either file: load_dotenv only
        assigns variables that exist in the file, so a deleted key stays in
        os.environ as a stale shadow until we explicitly pop it.
        """
        previously_known_keys = set(self._loaded_env_keys)
        currently_present: dict[str, set[str]] = {}

        if ENV_VAR_PATH.exists():
            file_keys = set(dotenv_values(ENV_VAR_PATH).keys())
            currently_present[str(ENV_VAR_PATH)] = file_keys
            load_dotenv(ENV_VAR_PATH, override=True)
        if self.workspace_env_path.exists():
            file_keys = set(dotenv_values(self.workspace_env_path).keys())
            currently_present[str(self.workspace_env_path)] = file_keys
            load_dotenv(self.workspace_env_path, override=True)

        present_anywhere = set().union(*currently_present.values()) if currently_present else set()
        for key in previously_known_keys - present_anywhere:
            os.environ.pop(key, None)

        self._loaded_env_keys = present_anywhere
        logger.debug("Refreshed secrets from .env files")

    @property
    def workspace_env_path(self) -> Path:
        return self.config_manager.workspace_path / ".env"

    @property
    def secrets_to_register(self) -> dict[str, str]:
        """Get secrets_to_register as a dict, normalizing list format to dict."""
        value = self.config_manager.get_config_value(SECRETS_TO_REGISTER_KEY, default={})
        return normalize_secrets_to_register(value)

    def register_all_secrets(self) -> None:
        """Register all secrets from config and library settings.

        This should be called after libraries are loaded and their settings
        are merged into the config.
        """
        for secret_name, default_value in self.secrets_to_register.items():
            if self.get_secret(secret_name, should_error_on_not_found=False) is None:
                self.set_secret(secret_name, default_value)

    def on_handle_get_secret_request(self, request: GetSecretValueRequest) -> ResultPayload:
        secret_key = SecretsManager._apply_secret_name_compliance(request.key)
        secret_value = self.get_secret(secret_key, should_error_on_not_found=request.should_error_on_not_found)

        if secret_value is None and request.should_error_on_not_found:
            details = f"Secret '{secret_key}' not found."
            logger.error(details)
            return GetSecretValueResultFailure(result_details=details)

        return GetSecretValueResultSuccess(
            value=secret_value, result_details=f"Successfully retrieved secret value for key: {secret_key}"
        )

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

        if self._event_manager is not None:
            self._event_manager.broadcast_app_event(SecretChanged(key=secret_name))
        self._notify_workers_to_refresh_secrets()

        return SetSecretValueResultSuccess(result_details=f"Successfully set secret value for key: {secret_name}")

    def on_handle_get_all_secret_values_request(self, request: GetAllSecretValuesRequest) -> ResultPayload:  # noqa: ARG002
        secret_values = dotenv_values(ENV_VAR_PATH)

        return GetAllSecretValuesResultSuccess(
            values=secret_values, result_details=f"Successfully retrieved {len(secret_values)} secret values"
        )

    def on_handle_delete_secret_value_request(self, request: DeleteSecretValueRequest) -> ResultPayload:
        secret_name = SecretsManager._apply_secret_name_compliance(request.key)

        if not ENV_VAR_PATH.exists():
            details = f"Secret file does not exist: '{ENV_VAR_PATH}'"
            logger.error(details)
            return DeleteSecretValueResultFailure(result_details=details)

        if get_key(ENV_VAR_PATH, secret_name) is None:
            details = f"Secret {secret_name} not found in {ENV_VAR_PATH}"
            logger.error(details)
            return DeleteSecretValueResultFailure(result_details=details)

        unset_key(ENV_VAR_PATH, secret_name)
        # set_secret writes through to os.environ via load_dotenv(override=True);
        # mirror that here so the orchestrator's own get_secret stops returning
        # the just-deleted value. Workers see the same drop after the refresh
        # broadcast lands -- refresh_from_env_file now pops keys that vanished
        # from the file, not just keys still present.
        os.environ.pop(secret_name, None)
        self._loaded_env_keys.discard(secret_name)

        logger.info("Secret '%s' deleted.", secret_name)

        if self._event_manager is not None:
            self._event_manager.broadcast_app_event(SecretChanged(key=secret_name))
        self._notify_workers_to_refresh_secrets()

        return DeleteSecretValueResultSuccess(result_details=f"Successfully deleted secret: {secret_name}")

    @overload
    def get_secret(self, secret_name: str, *, should_error_on_not_found: Literal[True] = True) -> str: ...

    @overload
    def get_secret(self, secret_name: str, *, should_error_on_not_found: Literal[False]) -> str | None: ...

    def get_secret(self, secret_name: str, *, should_error_on_not_found: bool = True) -> str | None:
        """Return the secret value with the following search precedence (highest to lowest priority).

        1. OS environment variables (highest priority)
        2. Workspace .env file (<workspace>/.env)
        3. Global .env file (~/.config/griptape_nodes/.env) (lowest priority)
        """
        secret_name = SecretsManager._apply_secret_name_compliance(secret_name)

        search_order = [
            ("environment variables", lambda: os.getenv(secret_name)),
            (str(self.workspace_env_path), lambda: DotEnv(self.workspace_env_path).get(secret_name)),
            (str(ENV_VAR_PATH), lambda: DotEnv(ENV_VAR_PATH).get(secret_name)),
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
        self._loaded_env_keys.add(secret_name)

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
