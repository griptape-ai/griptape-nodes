"""Engine command for Griptape Nodes CLI."""

from griptape_nodes.app import start_app
from griptape_nodes.cli.commands.init import _run_init
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
