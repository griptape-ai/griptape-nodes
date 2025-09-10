"""Self command for Griptape Nodes CLI."""

import shutil
import sys

import typer

from griptape_nodes.cli.shared import (
    CONFIG_DIR,
    DATA_DIR,
    GITHUB_UPDATE_URL,
    LATEST_TAG,
    PYPI_UPDATE_URL,
    console,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils.uv_utils import find_uv_bin
from griptape_nodes.utils.version_utils import (
    get_complete_version_string,
    get_current_version,
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
