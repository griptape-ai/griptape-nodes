"""Engine command for Griptape Nodes CLI."""

from rich.prompt import Confirm

from griptape_nodes.app import start_app
from griptape_nodes.cli.commands.init import _run_init
from griptape_nodes.cli.commands.self import _update_self
from griptape_nodes.cli.shared import (
    CONFIG_DIR,
    ENV_API_KEY,
    ENV_GTN_BUCKET_NAME,
    ENV_LIBRARIES_SYNC,
    ENV_REGISTER_ADVANCED_LIBRARY,
    ENV_STORAGE_BACKEND,
    ENV_WORKSPACE_DIRECTORY,
    InitConfig,
    console,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


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
    from griptape_nodes.retained_mode.events.app_events import (
        CheckEngineUpdateRequest,
        CheckEngineUpdateResultSuccess,
    )

    console.print("[bold green]Checking for updates...[/bold green]")

    request = CheckEngineUpdateRequest()
    result = GriptapeNodes.handle_request(request)

    if isinstance(result, CheckEngineUpdateResultSuccess) and result.update_available:
        current_version = result.current_version
        latest_version = result.latest_version
        install_source = result.install_source

        if install_source == "git":
            update_message = f"Your current engine version, {current_version} ({install_source}), doesn't match the latest release, {latest_version}. Update now?"
        else:
            update_message = f"Your current engine version, {current_version}, is behind the latest release, {latest_version}. Update now?"

        update = Confirm.ask(update_message, default=True)

        if update:
            _update_self()
