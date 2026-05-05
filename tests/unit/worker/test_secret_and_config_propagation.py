"""Integration tests for orchestrator->worker secret/config propagation.

Motivation
----------
Same-machine workers share ~/.config/griptape_nodes/.env and the global config
file with the orchestrator, but each process captures values in-memory at boot
(os.environ shadow for secrets; merged_config for config). A mutation on the
orchestrator that only rewrites the file is invisible to the worker until it
re-reads the file. PR #4477 closes that gap: after orchestrator-side handlers
mutate the shared state, WorkerManager fires WorkerRefreshSecretsRequest /
WorkerReloadConfigRequest at every registered worker, each of which re-reads
from disk.

These tests wire orchestrator-side SecretsManager/ConfigManager to a worker-
side pair via the InProcessWorkerHarness. Each test:

1. Boots both managers against a shared temporary XDG config home.
2. Primes the worker's in-memory cache with a boot value.
3. Dispatches a mutation on the orchestrator's manager.
4. Delivers the refresh/reload signal through the harness (standing in for
   WorkerManager.broadcast_to_workers, which is covered by unit tests).
5. Asserts the worker now sees the fresh value.

Intentional limits
------------------
- The harness does not start a real WorkerManager/transport; the signal is
  delivered by the test directly through harness.route_to_worker. Transport-
  side fan-out is already covered in tests/unit/app/test_app_worker.py
  (TestConfigReloadBroadcast / TestSecretRefreshBroadcast).
- No websocket serialization. Routing/forwarding shape is validated in
  test_harness_round_trip.py.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.events.base_events import EventRequest
from griptape_nodes.retained_mode.events.config_events import SetConfigValueRequest
from griptape_nodes.retained_mode.events.secrets_events import SetSecretValueRequest
from griptape_nodes.retained_mode.events.worker_events import (
    WorkerRefreshSecretsRequest,
    WorkerReloadConfigRequest,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
from tests.unit.worker.harness import InProcessWorkerHarness

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def shared_global_env(tmp_path: Path) -> Iterator[Path]:
    """Patch ENV_VAR_PATH so orchestrator and worker share one on-disk .env.

    Production has them share ~/.config/griptape_nodes/.env by virtue of
    running on the same machine. Patching to a tmp path isolates the test.
    """
    env_path = tmp_path / "global.env"
    with patch("griptape_nodes.retained_mode.managers.secrets_manager.ENV_VAR_PATH", env_path):
        yield env_path


@pytest.fixture
def shared_workspace(tmp_path: Path) -> Path:
    """A shared workspace directory both config managers anchor to."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="xdg_base_dirs cannot find XDG_CONFIG_HOME on Windows on GitHub Actions",
)
class TestSecretPropagation:
    """Orchestrator SetSecret should be visible to the worker after a refresh signal."""

    @pytest.mark.asyncio
    async def test_worker_reads_new_secret_after_refresh(
        self,
        shared_global_env: Path,
        shared_workspace: Path,
    ) -> None:
        secret_key = "INTEG_TEST_SECRET"
        # Prime the shared file and both processes' os.environ.
        shared_global_env.write_text(f"{secret_key}=boot_value\n")

        with patch.dict(os.environ, {secret_key: "boot_value"}, clear=False):
            harness = InProcessWorkerHarness()
            orchestrator_config = ConfigManager()
            orchestrator_config.workspace_path = shared_workspace
            orchestrator_secrets = SecretsManager(orchestrator_config, event_manager=harness.orchestrator)

            worker_config = ConfigManager()
            worker_config.workspace_path = shared_workspace
            worker_secrets = SecretsManager(worker_config, event_manager=harness.worker)

            # Sanity: both sides see the boot value before anything happens.
            assert orchestrator_secrets.get_secret(secret_key) == "boot_value"
            assert worker_secrets.get_secret(secret_key) == "boot_value"

            await harness.start()
            try:
                # Orchestrator mutates the secret. The handler writes the file and
                # schedules a worker broadcast, but the harness has no real
                # WorkerManager transport, so nothing reaches the worker yet.
                orchestrator_secrets.on_handle_set_secret_request(
                    SetSecretValueRequest(key=secret_key, value="updated_value"),
                )
                assert orchestrator_secrets.get_secret(secret_key) == "updated_value"

                # Worker's os.environ shadow is still stale because no refresh
                # signal has been delivered. get_secret hits env var first.
                assert os.environ[secret_key] == "updated_value"  # orchestrator write-through
                # ^ Note: orchestrator's set_secret uses load_dotenv(override=True),
                # so on the same process os.environ ends up with the new value.
                # This is fine on a single machine because secrets ride os.environ
                # across the process boundary via the shared file.

                # Deliver the refresh signal through the harness. This is the
                # moral equivalent of WorkerManager broadcasting
                # WorkerRefreshSecretsRequest to every registered worker.
                await harness.route_to_worker(EventRequest(request=WorkerRefreshSecretsRequest()))

                # Worker now sees the fresh value.
                assert worker_secrets.get_secret(secret_key) == "updated_value"
            finally:
                await harness.stop()

    @pytest.mark.asyncio
    async def test_worker_holds_stale_value_until_refresh_arrives(
        self,
        shared_global_env: Path,
        shared_workspace: Path,
    ) -> None:
        """Without the refresh signal, a worker whose os.environ was set at boot
        keeps returning the old value even after the orchestrator rewrites the
        shared file. This is the motivating bug for PR #4477.
        """
        secret_key = "INTEG_STALE_SECRET"
        shared_global_env.write_text(f"{secret_key}=boot_value\n")

        # Only the worker side has the old value in its environment. The
        # orchestrator side will write through load_dotenv(override=True).
        with patch.dict(os.environ, {secret_key: "boot_value"}, clear=False):
            harness = InProcessWorkerHarness()
            worker_config = ConfigManager()
            worker_config.workspace_path = shared_workspace
            worker_secrets = SecretsManager(worker_config, event_manager=harness.worker)

            assert worker_secrets.get_secret(secret_key) == "boot_value"

            # Someone else (the orchestrator in production) rewrites the file.
            shared_global_env.write_text(f"{secret_key}=external_update\n")

            # Without a refresh, the worker still returns the boot value because
            # os.environ is consulted first and has not been touched.
            assert worker_secrets.get_secret(secret_key) == "boot_value"

            # Now run the refresh path. This is what on_handle_worker_refresh_secrets_request
            # does on a real worker.
            await harness.start()
            try:
                await harness.route_to_worker(EventRequest(request=WorkerRefreshSecretsRequest()))
            finally:
                await harness.stop()

            assert worker_secrets.get_secret(secret_key) == "external_update"


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="xdg_base_dirs cannot find XDG_CONFIG_HOME on Windows on GitHub Actions",
)
class TestConfigPropagation:
    """Orchestrator SetConfigValue should be visible to the worker after a reload signal."""

    @pytest.mark.asyncio
    async def test_worker_reads_new_config_after_reload(
        self,
        shared_workspace: Path,
        tmp_path: Path,
    ) -> None:
        shared_user_config = tmp_path / "griptape_nodes_config.json"
        shared_user_config.write_text('{"nested": {"key": "boot_value"}}\n')

        with patch(
            "griptape_nodes.retained_mode.managers.config_manager.USER_CONFIG_PATH",
            shared_user_config,
        ):
            harness = InProcessWorkerHarness()
            orchestrator_config = ConfigManager(event_manager=harness.orchestrator)
            orchestrator_config.workspace_path = shared_workspace
            worker_config = ConfigManager(event_manager=harness.worker)
            worker_config.workspace_path = shared_workspace

            # Both see boot value.
            assert orchestrator_config.get_config_value("nested.key") == "boot_value"
            assert worker_config.get_config_value("nested.key") == "boot_value"

            await harness.start()
            try:
                # Orchestrator writes the new value via its request handler.
                orchestrator_config.on_handle_set_config_value_request(
                    SetConfigValueRequest(category_and_key="nested.key", value="updated_value"),
                )
                assert orchestrator_config.get_config_value("nested.key") == "updated_value"

                # Worker still has the stale merged_config.
                assert worker_config.get_config_value("nested.key") == "boot_value"

                # Deliver the reload signal.
                await harness.route_to_worker(EventRequest(request=WorkerReloadConfigRequest()))

                assert worker_config.get_config_value("nested.key") == "updated_value"
            finally:
                await harness.stop()
