"""Self command for Griptape Nodes CLI."""

import shutil

import typer

from griptape_nodes.cli.shared import (
    CONFIG_DIR,
    DATA_DIR,
    console,
)
from griptape_nodes.retained_mode.events.app_events import UpdateEngineRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils.uv_utils import find_uv_bin
from griptape_nodes.utils.version_utils import get_complete_version_string

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


def _update_self() -> None:
    """Installs the latest release of the CLI *and* refreshes bundled libraries."""
    request = UpdateEngineRequest()
    GriptapeNodes.handle_request(request)


def _auto_update_self() -> None:
    """Automatically checks for and applies engine updates based on the auto_update_engine setting."""
    from rich.prompt import Confirm

    from griptape_nodes.retained_mode.events.app_events import (
        CheckEngineUpdateRequest,
        CheckEngineUpdateResultSuccess,
    )
    from griptape_nodes.retained_mode.managers.settings import AutoUpdateMode

    # Get the auto-update setting
    auto_update_mode_str = config_manager.get_config_value("auto_update_engine", default="prompt")
    auto_update_mode = AutoUpdateMode(auto_update_mode_str)

    # If auto-update is disabled, skip entirely
    if auto_update_mode == AutoUpdateMode.OFF:
        return

    console.print("[bold green]Checking for updates...[/bold green]")

    request = CheckEngineUpdateRequest()
    result = GriptapeNodes.handle_request(request)

    if not isinstance(result, CheckEngineUpdateResultSuccess):
        return

    if not result.update_available:
        return

    current_version = result.current_version
    latest_version = result.latest_version
    install_source = result.install_source

    # Handle "on" mode - auto-update without prompting
    if auto_update_mode == AutoUpdateMode.ON:
        console.print(
            f"[bold green]Update available: {current_version} -> {latest_version}. Auto-updating...[/bold green]"
        )
        _update_self()
        return

    # Handle "prompt" mode - ask the user
    if install_source == "git":
        update_message = f"Your current engine version, {current_version} ({install_source}), doesn't match the latest release, {latest_version}. Update now?"
    else:
        update_message = f"Your current engine version, {current_version}, is behind the latest release, {latest_version}. Update now?"

    update = Confirm.ask(update_message, default=True)

    if update:
        _update_self()


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
