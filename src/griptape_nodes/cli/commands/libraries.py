"""Libraries command for Griptape Nodes CLI."""

import asyncio
import shutil
import tarfile
import tempfile
from pathlib import Path

import httpx
import typer
from rich.progress import Progress

from griptape_nodes.cli.shared import (
    ENV_LIBRARIES_BASE_DIR,
    LATEST_TAG,
    NODES_TARBALL_URL,
    console,
)
from griptape_nodes.retained_mode.events.os_events import DeleteFileRequest, DeleteFileResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils.version_utils import get_current_version, get_install_source

app = typer.Typer(help="Manage local libraries.")


@app.command()
def sync() -> None:
    """Sync libraries with your current engine version."""
    asyncio.run(_sync_libraries())


async def _sync_libraries(*, load_libraries_from_config: bool = True) -> None:
    """Download and sync Griptape Nodes libraries, copying only directories from synced libraries.

    Args:
        load_libraries_from_config (bool): If True, re-initialize all libraries from config

    """
    install_source, _ = get_install_source()
    # Unless we're installed from PyPi, grab libraries from the 'latest' tag
    if install_source == "pypi":
        version = get_current_version()
    else:
        version = LATEST_TAG

    console.print(f"[bold cyan]Fetching Griptape Nodes libraries ({version})...[/bold cyan]")

    tar_url = NODES_TARBALL_URL.format(tag=version)
    console.print(f"[green]Downloading from {tar_url}[/green]")
    dest_nodes = Path(ENV_LIBRARIES_BASE_DIR)

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "nodes.tar.gz"

        # Streaming download with a tiny progress bar
        with httpx.stream("GET", tar_url, follow_redirects=True) as r, Progress() as progress:
            task = progress.add_task("[green]Downloading...", total=int(r.headers.get("Content-Length", 0)))
            progress.start()
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                console.print(f"[red]Error fetching libraries: {e}[/red]")
                return
            with tar_path.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))

        console.print("[green]Extracting...[/green]")
        # Extract and locate extracted directory
        with tarfile.open(tar_path) as tar:
            tar.extractall(tmp, filter="data")

        extracted_root = next(Path(tmp).glob("griptape-nodes-*"))
        extracted_libs = extracted_root / "libraries"

        # Copy directories from synced libraries without removing existing content
        console.print(f"[green]Syncing libraries to {dest_nodes.resolve()}...[/green]")
        dest_nodes.mkdir(parents=True, exist_ok=True)
        for library_dir in extracted_libs.iterdir():
            if library_dir.is_dir():
                dest_library_dir = dest_nodes / library_dir.name
                if dest_library_dir.exists():
                    # Use DeleteFileRequest for centralized deletion with Windows compatibility
                    request = DeleteFileRequest(path=str(dest_library_dir), workspace_only=False)
                    result = await GriptapeNodes.OSManager().on_delete_file_request(request)
                    if not isinstance(result, DeleteFileResultSuccess):
                        console.print(f"[yellow]Warning: Failed to delete existing library {library_dir.name}[/yellow]")
                shutil.copytree(library_dir, dest_library_dir)
                console.print(f"[green]Synced library: {library_dir.name}[/green]")

    # Re-initialize all libraries from config
    if load_libraries_from_config:
        console.print("[bold cyan]Initializing libraries...[/bold cyan]")
        try:
            await GriptapeNodes.LibraryManager().load_all_libraries_from_config()
            console.print("[bold green]Libraries Initialized successfully.[/bold green]")
        except Exception as e:
            console.print(f"[red]Error initializing libraries: {e}[/red]")

    console.print("[bold green]Libraries synced.[/bold green]")
