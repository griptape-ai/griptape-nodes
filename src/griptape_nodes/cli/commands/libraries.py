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
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromFileResultFailure,
    RegisterLibraryFromFileResultSuccess,
    RegisterLibraryFromGitRepoRequest,
    RegisterLibraryFromGitRepoResultFailure,
    RegisterLibraryFromGitRepoResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils.git_utils import is_git_url
from griptape_nodes.utils.version_utils import get_current_version, get_install_source

app = typer.Typer(help="Manage local libraries.")


@app.command()
def sync() -> None:
    """Sync libraries with your current engine version."""
    asyncio.run(_sync_libraries())


@app.command()
def register(
    source: str = typer.Argument(..., help="Library source: file path (.json) or Git URL"),
    branch: str | None = typer.Option(
        None, "--branch", "-b", help="Git branch to checkout (overrides URL auto-detection)"
    ),
    subdir: str | None = typer.Option(
        None, "--subdir", "-s", help="Subdirectory path within repository (overrides URL auto-detection)"
    ),
) -> None:
    """Register a library from a file or Git repository."""
    asyncio.run(_register_library(source, branch, subdir))


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


async def _register_library(source: str, branch: str | None, subdir: str | None) -> None:
    """Register a library from a file path or Git repository.

    Args:
        source: Library source (file path or Git URL)
        branch: Git branch to checkout (overrides URL auto-detection)
        subdir: Subdirectory path (overrides URL auto-detection)
    """
    # Initialize GriptapeNodes to ensure managers are available
    griptape_nodes = GriptapeNodes()

    # Determine if source is a Git URL or file path
    if is_git_url(source):
        await _register_git_library(griptape_nodes, source, branch, subdir)
    else:
        await _register_file_library(griptape_nodes, source)


async def _register_git_library(
    griptape_nodes: GriptapeNodes, source: str, branch: str | None, subdir: str | None
) -> None:
    """Register a library from a Git repository."""
    console.print(f"[bold cyan]Registering library from Git repository: {source}[/bold cyan]")

    # Create the request with raw URL and overrides
    request = RegisterLibraryFromGitRepoRequest(git_url=source, branch_override=branch, subdir_override=subdir)

    try:
        result = await griptape_nodes.LibraryManager().register_library_from_git_repo_request(request)

        if isinstance(result, RegisterLibraryFromGitRepoResultSuccess):
            console.print(f"[bold green]Successfully registered library: {result.library_name}[/bold green]")
        elif isinstance(result, RegisterLibraryFromGitRepoResultFailure):
            console.print(f"[red]Failed to register library: {result.result_details}[/red]")
        else:
            console.print(f"[red]Unexpected result type: {type(result)}[/red]")

    except Exception as e:
        console.print(f"[red]Error registering Git library: {e}[/red]")


async def _register_file_library(griptape_nodes: GriptapeNodes, source: str) -> None:
    """Register a library from a file path."""
    source_path = Path(source)

    if not source_path.exists():
        console.print(f"[red]File not found: {source}[/red]")
        return

    if source_path.suffix != ".json":
        console.print(f"[red]Library file must have .json extension: {source}[/red]")
        return

    console.print(f"[bold cyan]Registering library from file: {source}[/bold cyan]")

    request = RegisterLibraryFromFileRequest(file_path=str(source_path.absolute()), load_as_default_library=False)

    try:
        result = await griptape_nodes.LibraryManager().register_library_from_file_request(request)

        if isinstance(result, RegisterLibraryFromFileResultSuccess):
            console.print(f"[bold green]Successfully registered library: {result.library_name}[/bold green]")
        elif isinstance(result, RegisterLibraryFromFileResultFailure):
            console.print(f"[red]Failed to register library: {result.result_details}[/red]")
        else:
            console.print(f"[red]Unexpected result type: {type(result)}[/red]")

    except Exception as e:
        console.print(f"[red]Error registering file library: {e}[/red]")
