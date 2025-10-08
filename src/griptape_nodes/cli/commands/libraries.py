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
from griptape_nodes.retained_mode.events.library_events import (
    DownloadLibraryRequest,
    DownloadLibraryResultFailure,
    DownloadLibraryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils.version_utils import get_current_version, get_install_source

app = typer.Typer(help="Manage local libraries.")


@app.command()
def sync() -> None:
    """Sync libraries with your current engine version."""
    asyncio.run(_sync_libraries())


@app.command()
def download(
    url: str, *, force: bool = typer.Option(False, "--force", "-f", help="Override existing library if it exists")
) -> None:
    """Download a library from a GitHub repository URL.

    Args:
        url: GitHub repository URL (e.g., https://github.com/org/repo or org/repo)
        force: If True, override existing library directory
    """
    console.print(f"[bold cyan]Downloading library from {url}...[/bold cyan]")

    request = DownloadLibraryRequest(url=url, override_existing=force)
    result = GriptapeNodes.handle_request(request)

    if isinstance(result, DownloadLibraryResultSuccess):
        console.print(f"[bold green]Successfully downloaded library: {result.library_name}[/bold green]")
        console.print(f"[green]Location: {result.library_path}[/green]")
    elif isinstance(result, DownloadLibraryResultFailure):
        # Extract messages from result details
        detail_messages = [detail.message for detail in result.result_details.result_details]

        # Check if failure is due to existing directory
        is_existing_dir_error = any("Directory already exists" in message for message in detail_messages)

        console.print(f"[bold red]Failed to download library from {url}[/bold red]")
        for message in detail_messages:
            console.print(f"[red]- {message}[/red]")

        # If it's an existing directory error and we didn't use --force, prompt the user
        if is_existing_dir_error and not force:
            should_override = typer.confirm("\nDo you want to override the existing library?", default=False)
            if should_override:
                console.print("[bold cyan]Retrying download with override...[/bold cyan]")
                retry_request = DownloadLibraryRequest(url=url, override_existing=True)
                retry_result = GriptapeNodes.handle_request(retry_request)

                if isinstance(retry_result, DownloadLibraryResultSuccess):
                    console.print(
                        f"[bold green]Successfully downloaded library: {retry_result.library_name}[/bold green]"
                    )
                    console.print(f"[green]Location: {retry_result.library_path}[/green]")
                elif isinstance(retry_result, DownloadLibraryResultFailure):
                    retry_messages = [detail.message for detail in retry_result.result_details.result_details]
                    console.print(f"[bold red]Failed to download library from {url}[/bold red]")
                    for message in retry_messages:
                        console.print(f"[red]- {message}[/red]")


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
                    shutil.rmtree(dest_library_dir)
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
