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
    _download_and_run_installer()
    if os_manager.is_windows():
        # On Windows, the terminal prompt doesn't refresh after the update finishes.
        # This gives the appearance of the program hanging, but it is not.
        # This is a workaround to manually refresh the terminal.
        console.print("[bold yellow]Please press Enter to exit updater...[/bold yellow]")


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
        console.print(f"[bold red]Error during update: {e}[/bold red]")
    else:
        console.print("[bold green]Finished updating self.[/bold green]")
        console.print("[bold green]Run 'griptape-nodes' (or 'gtn') to restart the engine.[/bold green]")


if __name__ == "__main__":
    main()
