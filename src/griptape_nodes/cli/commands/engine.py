"""Engine command for Griptape Nodes CLI."""

from rich.prompt import Confirm

from griptape_nodes.app import start_app
from griptape_nodes.cli.commands.init import _run_init
from griptape_nodes.cli.commands.self import _get_latest_version, _update_self
from griptape_nodes.cli.shared import (
    CONFIG_DIR,
    ENV_API_KEY,
    ENV_GTN_BUCKET_NAME,
    ENV_LIBRARIES_SYNC,
    ENV_REGISTER_ADVANCED_LIBRARY,
    ENV_STORAGE_BACKEND,
    ENV_WORKSPACE_DIRECTORY,
    PACKAGE_NAME,
    InitConfig,
    console,
)
from griptape_nodes.utils.version_utils import get_current_version, get_install_source


def engine_command() -> None:
    """Run the Griptape Nodes engine."""
    _start_engine()


def _start_engine() -> None:
    """Starts the Griptape Nodes engine."""
    if not CONFIG_DIR.exists():
        # Default init flow if there is no config directory
        console.print("[bold green]Config directory not found. Initializing...[/bold green]")
        _run_init(
            InitConfig(
                workspace_directory=ENV_WORKSPACE_DIRECTORY,
                api_key=ENV_API_KEY,
                storage_backend=ENV_STORAGE_BACKEND,
                register_advanced_library=ENV_REGISTER_ADVANCED_LIBRARY,
                interactive=True,
                config_values=None,
                secret_values=None,
                libraries_sync=ENV_LIBRARIES_SYNC,
                bucket_name=ENV_GTN_BUCKET_NAME,
            )
        )

    console.print("[bold green]Starting Griptape Nodes engine...[/bold green]")
    start_app()


def _auto_update_self() -> None:
    """Automatically updates the script to the latest version if the user confirms."""
    console.print("[bold green]Checking for updates...[/bold green]")
    source, commit_id = get_install_source()
    current_version = get_current_version()
    latest_version = _get_latest_version(PACKAGE_NAME, source)

    if source == "git" and commit_id is not None:
        can_update = commit_id != latest_version
        update_message = f"Your current engine version, {current_version} ({source} - {commit_id}), doesn't match the latest release, {latest_version}. Update now?"
    else:
        can_update = current_version < latest_version
        update_message = f"Your current engine version, {current_version}, is behind the latest release, {latest_version}. Update now?"

    if can_update:
        update = Confirm.ask(update_message, default=True)

        if update:
            _update_self()
