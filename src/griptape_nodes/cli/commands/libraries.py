"""Libraries command for Griptape Nodes CLI."""

import asyncio

import typer

from griptape_nodes.cli.shared import console
from griptape_nodes.retained_mode.events.library_events import (
    DownloadLibraryRequest,
    DownloadLibraryResultSuccess,
    SyncLibrariesRequest,
    SyncLibrariesResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils.git_utils import normalize_github_url

app = typer.Typer(help="Manage local libraries.")


@app.command()
def sync(
    overwrite: bool = typer.Option(False, "--overwrite", help="Discard uncommitted changes in libraries"),  # noqa: FBT001
) -> None:
    """Sync all libraries to latest versions from their git repositories."""
    asyncio.run(_sync_libraries(overwrite_existing=overwrite))


async def _sync_libraries(*, overwrite_existing: bool) -> None:
    """Sync all libraries by checking for updates and installing dependencies."""
    console.print("[bold cyan]Syncing libraries...[/bold cyan]")

    # Create sync request with provided parameters
    request = SyncLibrariesRequest(
        overwrite_existing=overwrite_existing,
    )

    # Execute the sync
    result = await GriptapeNodes.ahandle_request(request)

    # Display results - failure case first
    if not isinstance(result, SyncLibrariesResultSuccess):
        console.print(f"[red]Failed to sync libraries: {result.result_details}[/red]")
        return

    # Success path
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

    console.print("[bold green]Libraries synced successfully.[/bold green]")


@app.command()
def download(
    git_url: str = typer.Argument(..., help="Git repository URL to download"),
    branch: str | None = typer.Option(None, "--branch", help="Branch, tag, or commit to checkout"),
    target_dir: str | None = typer.Option(None, "--target-dir", help="Target directory name"),
    download_dir: str | None = typer.Option(None, "--download-dir", help="Parent directory for library download"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing library directory if it exists"),  # noqa: FBT001
) -> None:
    """Download a library from a git repository."""
    asyncio.run(_download_library(git_url, branch, target_dir, download_dir, overwrite_existing=overwrite))


async def _download_library(
    git_url: str,
    branch_tag_commit: str | None,
    target_directory_name: str | None,
    download_directory: str | None,
    *,
    overwrite_existing: bool,
) -> None:
    """Download a library from a git repository."""
    # Normalize GitHub shorthand to full URL
    git_url = normalize_github_url(git_url)

    console.print(f"[bold cyan]Downloading library from {git_url}...[/bold cyan]")

    # Create the download request
    request = DownloadLibraryRequest(
        git_url=git_url,
        branch_tag_commit=branch_tag_commit,
        target_directory_name=target_directory_name,
        download_directory=download_directory,
        overwrite_existing=overwrite_existing,
    )

    # Execute the download
    result = await GriptapeNodes.ahandle_request(request)

    # Display results - failure case first
    if not isinstance(result, DownloadLibraryResultSuccess):
        console.print(f"[red]Failed to download library: {result.result_details}[/red]")
        return

    # Success path
    console.print(f"[bold green]Library '{result.library_name}' downloaded successfully![/bold green]")
    console.print(f"[green]Downloaded to: {result.library_path}[/green]")
