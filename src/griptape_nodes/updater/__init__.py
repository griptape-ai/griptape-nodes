"""Runs *outside* the main process, so its own files are the only ones locked.

Usage:
    python -m griptape_nodes.updater            # update only
"""

from __future__ import annotations

import subprocess

from rich.console import Console

from griptape_nodes.retained_mode.managers.os_manager import OSManager

console = Console()

os_manager = OSManager()


def main() -> None:
    """Entry point for the updater CLI."""
    try:
        _download_and_run_installer()
        _sync_assets()
    except subprocess.CalledProcessError:
        console.print("[red]Error during update process.[/red]")
    else:
        console.print("[green]Finished updating self.[/green]")
        console.print("[green]Run 'griptape-nodes' (or 'gtn') to restart the engine.[/green]")
        if os_manager.is_windows():
            # On Windows, the terminal prompt doesn't refresh after the update finishes.
            # This gives the appearance of the program hanging, but it is not.
            # This is a workaround to manually refresh the terminal.
            console.print("[yellow]Please press Enter to exit updater...[/yellow]")


def _download_and_run_installer() -> None:
    """Runs the update commands for the engine."""
    console.print("[bold green]Updating self...[/bold green]")
    try:
        subprocess.run(  # noqa: S603
            ["uv", "tool", "upgrade", "griptape-nodes"],  # noqa: S607
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error during update: {e}[/red]")
        raise
    else:
        console.print("[green]Finished updating self.[/green]")


def _sync_assets() -> None:
    """Syncs the assets for the engine."""
    console.print("[bold green]Syncing assets...[/bold green]")
    try:
        subprocess.run(  # noqa: S603
            ["griptape-nodes", "assets", "sync"],  # noqa: S607
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error during asset sync: {e}[/red]")
        raise
    else:
        console.print("[green]Finished syncing assets.[/green]")


if __name__ == "__main__":
    main()
