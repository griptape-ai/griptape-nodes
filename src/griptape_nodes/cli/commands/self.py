"""Self command for Griptape Nodes CLI."""

import asyncio
import json
import platform
import shutil
import sys

import typer
from rich.table import Table

from griptape_nodes.cli.shared import (
    CONFIG_DIR,
    CONFIG_FILE,
    DATA_DIR,
    GITHUB_UPDATE_URL,
    LATEST_TAG,
    PYPI_UPDATE_URL,
    console,
)
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.library_events import LoadLibrariesRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils.uv_utils import find_uv_bin
from griptape_nodes.utils.version_utils import (
    get_complete_version_string,
    get_current_version,
    get_install_source,
    get_latest_version_git,
    get_latest_version_pypi,
)

config_manager = GriptapeNodes.ConfigManager()
secrets_manager = GriptapeNodes.SecretsManager()
os_manager = GriptapeNodes.OSManager()

app = typer.Typer(help="Manage this CLI installation.")


@app.command()
def update() -> None:
    """Update the CLI."""
    _update_self()


@app.command()
def uninstall() -> None:
    """Uninstall the CLI."""
    _uninstall_self()


@app.command()
def version() -> None:
    """Print the CLI version."""
    _print_current_version()


@app.command()
def info() -> None:
    """Display system information for debugging."""
    asyncio.run(_print_system_info_async())


def _get_latest_version(package: str, install_source: str) -> str:
    """Fetches the latest release tag from PyPI.

    Args:
        package: The name of the package to fetch the latest version for.
        install_source: The source from which the package is installed (e.g., "pypi", "git", "file").

    Returns:
        str: Latest release tag (e.g., "v0.31.4")
    """
    if install_source == "pypi":
        return get_latest_version_pypi(package, PYPI_UPDATE_URL)
    if install_source == "git":
        return get_latest_version_git(package, GITHUB_UPDATE_URL, LATEST_TAG)
    # If the package is installed from a file, just return the current version since the user is likely managing it manually
    return get_current_version()


def _update_self() -> None:
    """Installs the latest release of the CLI *and* refreshes bundled libraries."""
    console.print("[bold green]Starting updater...[/bold green]")

    os_manager.replace_process([sys.executable, "-m", "griptape_nodes.updater"])


def _print_current_version() -> None:
    """Prints the current version of the script."""
    version_string = get_complete_version_string()
    console.print(f"[bold green]{version_string}[/bold green]")


def _uninstall_self() -> None:
    """Uninstalls itself by removing config/data directories and the executable."""
    console.print("[bold]Uninstalling Griptape Nodes...[/bold]")

    # Remove config and data directories
    console.print("[bold]Removing config and data directories...[/bold]")
    dirs = [(CONFIG_DIR, "Config Dir"), (DATA_DIR, "Data Dir")]
    caveats = []
    for dir_path, dir_name in dirs:
        if dir_path.exists():
            console.print(f"[bold]Removing {dir_name} '{dir_path}'...[/bold]")
            try:
                shutil.rmtree(dir_path)
            except OSError as exc:
                console.print(f"[red]Error removing {dir_name} '{dir_path}': {exc}[/red]")
                caveats.append(
                    f"- [red]Error removing {dir_name} '{dir_path}'. You may want remove this directory manually.[/red]"
                )
        else:
            console.print(f"[yellow]{dir_name} '{dir_path}' does not exist; skipping.[/yellow]")

    # Handle any remaining config files not removed by design
    remaining_config_files = config_manager.config_files
    if remaining_config_files:
        caveats.append("- Some config files were intentionally not removed:")
        caveats.extend(f"\t[yellow]- {file}[/yellow]" for file in remaining_config_files)

    # If there were any caveats to the uninstallation process, print them
    if caveats:
        console.print("[bold]Caveats:[/bold]")
        for line in caveats:
            console.print(line)

    # Remove the executable
    console.print("[bold]Removing the executable...[/bold]")
    console.print("[bold yellow]When done, press Enter to exit.[/bold yellow]")

    # Remove the tool using UV
    uv_path = find_uv_bin()
    os_manager.replace_process([uv_path, "tool", "uninstall", "griptape-nodes"])


async def _print_system_info_async() -> None:
    """Print comprehensive system information (async wrapper to load libraries)."""
    # Load libraries from configuration first
    load_request = LoadLibrariesRequest()
    await GriptapeNodes.ahandle_request(load_request)

    # Now print all the info
    _print_system_info()


def _print_system_info() -> None:
    """Print comprehensive system information."""
    console.print("\n[bold cyan]Griptape Nodes System Information[/bold cyan]\n")

    _print_engine_info()
    _print_platform_info()
    _print_paths_info()
    _print_configuration()
    _print_registered_libraries()


def _print_engine_info() -> None:
    """Print engine version information."""
    version_string = get_complete_version_string()
    install_source, commit_id = get_install_source()

    console.print("[bold]Engine:[/bold]")
    console.print(f"  Version: {version_string}")
    console.print(f"  Install Source: {install_source}")
    if commit_id:
        console.print(f"  Commit ID: {commit_id}")
    console.print()


def _print_platform_info() -> None:
    """Print platform information."""
    console.print("[bold]Platform:[/bold]")
    console.print(f"  OS: {platform.system()}")
    console.print(f"  OS Version: {platform.version()}")
    console.print(f"  OS Release: {platform.release()}")
    console.print(f"  Architecture: {platform.machine()}")
    console.print(f"  Python Version: {platform.python_version()}")
    console.print(f"  Python Implementation: {platform.python_implementation()}")
    console.print(f"  Python Executable: {sys.executable}")
    console.print()


def _print_paths_info() -> None:
    """Print configuration paths."""
    console.print("[bold]Paths:[/bold]")
    console.print(f"  Config Directory: {CONFIG_DIR}")
    console.print(f"  Config File: {CONFIG_FILE}")
    console.print(f"  Data Directory: {DATA_DIR}")

    workspace_dir = config_manager.get_config_value("file_system.directories.workspace_directory")
    if workspace_dir:
        console.print(f"  Workspace Directory: {workspace_dir}")
    console.print()


def _print_configuration() -> None:
    """Print full configuration."""
    console.print("[bold]Configuration:[/bold]")
    try:
        full_config = config_manager.merged_config
        config_json = json.dumps(full_config, indent=2, default=str)
        console.print(f"[dim]{config_json}[/dim]")
    except Exception as e:
        console.print(f"  [red]Error retrieving configuration: {e}[/red]")
    console.print()


def _print_registered_libraries() -> None:
    """Print registered libraries information."""
    console.print("[bold]Registered Libraries:[/bold]")
    try:
        library_names = LibraryRegistry.list_libraries()
        if not library_names:
            console.print("  [yellow]No libraries registered[/yellow]")
            console.print()
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Library Name", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Engine Version", style="yellow")
        table.add_column("Author", style="blue")

        for library_name in library_names:
            try:
                library = LibraryRegistry.get_library(library_name)
                metadata = library.get_metadata()
                table.add_row(
                    library_name,
                    metadata.library_version,
                    metadata.engine_version,
                    metadata.author,
                )
            except KeyError:
                table.add_row(library_name, "[red]Error[/red]", "[red]Error[/red]", "[red]Error[/red]")

        console.print(table)
    except Exception as e:
        console.print(f"  [red]Error retrieving libraries: {e}[/red]")
    console.print()
