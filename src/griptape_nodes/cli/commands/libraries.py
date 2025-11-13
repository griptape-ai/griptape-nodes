"""Libraries command for Griptape Nodes CLI."""

import asyncio

import typer

from griptape_nodes.cli.shared import console
from griptape_nodes.retained_mode.events.library_events import (
    LoadLibrariesRequest,
    SyncLibrariesRequest,
    SyncLibrariesResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

app = typer.Typer(help="Manage local libraries.")


@app.command()
def sync() -> None:
    """Sync all libraries to latest versions from their git repositories."""
    asyncio.run(_sync_libraries())


async def _sync_libraries() -> None:
    """Sync all libraries by checking for updates and installing dependencies."""
    console.print("[bold cyan]Loading libraries...[/bold cyan]")

    # First, load libraries from configuration
    load_request = LoadLibrariesRequest()
    load_result = await GriptapeNodes.ahandle_request(load_request)
    if not load_result.succeeded():
        console.print(f"[red]Failed to load libraries: {load_result.result_details}[/red]")
        return

    console.print("[bold cyan]Syncing libraries...[/bold cyan]")

    # Create sync request with default parameters
    request = SyncLibrariesRequest(
        check_updates_only=False,
        install_dependencies=True,
        exclude_libraries=None,
    )

    # Execute the sync
    result = await GriptapeNodes.ahandle_request(request)

    # Display results
    if isinstance(result, SyncLibrariesResultSuccess):
        console.print(f"[green]Checked {result.libraries_checked} libraries[/green]")

        if result.libraries_updated > 0:
            console.print(f"[bold green]Updated {result.libraries_updated} libraries:[/bold green]")
            for lib_name, update_info in result.update_summary.items():
                if update_info.get("status") == "updated":
                    console.print(
                        f"  [green]✓ {lib_name}: {update_info['old_version']} → {update_info['new_version']}[/green]"
                    )
                elif update_info.get("status") == "failed":
                    console.print(f"  [red]✗ {lib_name}: {update_info.get('error', 'Unknown error')}[/red]")
        else:
            console.print("[green]All libraries are up to date[/green]")

        if result.libraries_skipped > 0:
            console.print(f"[yellow]Skipped {result.libraries_skipped} libraries[/yellow]")

        console.print("[bold green]Libraries synced successfully.[/bold green]")
    else:
        console.print(f"[red]Failed to sync libraries: {result.result_details}[/red]")
