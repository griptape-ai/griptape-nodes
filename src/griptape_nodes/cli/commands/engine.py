"""Engine command for Griptape Nodes CLI."""

from typing import Annotated

import typer

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


def engine_command(
    session_id: Annotated[
        str | None,
        typer.Option(
            "--session-id",
            envvar="GTN_SESSION_ID",
            help="Session ID of an existing orchestrator session to join as a worker engine.",
        ),
    ] = None,
    library_name: Annotated[
        str | None,
        typer.Option(
            "--library-name",
            envvar="GTN_LIBRARY_NAME",
            help="If set, this engine serves only the named library and loads no other libraries.",
        ),
    ] = None,
) -> None:
    """Run the Griptape Nodes engine."""
    _start_engine(worker_session_id=session_id, worker_library_name=library_name)


def _start_engine(worker_session_id: str | None = None, worker_library_name: str | None = None) -> None:
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

    if not worker_session_id:
        console.print("[bold green]Starting Griptape Nodes engine...[/bold green]")
    start_app(worker_session_id=worker_session_id, worker_library_name=worker_library_name)
