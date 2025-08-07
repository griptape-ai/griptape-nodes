"""Runs *outside* the main process, so its own files are the only ones locked.

Usage:
    python -m griptape_nodes.updater            # update only
"""

from __future__ import annotations

import subprocess

from rich.console import Console

from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.utils.uv_utils import find_uv_bin

console = Console()

os_manager = OSManager()


def main() -> None:
    """Entry point for the updater CLI."""
    try:
        _download_and_run_installer()
        _sync_libraries()
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
        uv_path = find_uv_bin()
        subprocess.run(  # noqa: S603
            [uv_path, "tool", "upgrade", "griptape-nodes"],
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(
            f"[red]Error during update: return code={e.returncode}, stdout={e.stdout}, stderr={e.stderr}[/red]"
        )
        raise
    else:
        console.print("[green]Finished updating self.[/green]")


def _sync_libraries() -> None:
    """Syncs the libraries for the engine."""
    console.print("[bold green]Syncing libraries...[/bold green]")
    try:
        subprocess.run(
            ["griptape-nodes", "libraries", "sync"],  # noqa: S607
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(
            f"[red]Error during libraries sync: return code={e.returncode}, stdout={e.stdout}, stderr={e.stderr}[/red]"
        )
        raise
    else:
        console.print("[green]Finished syncing libraries.[/green]")


if __name__ == "__main__":
    main()
