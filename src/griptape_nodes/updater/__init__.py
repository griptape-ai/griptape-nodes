"""Runs *outside* the main process, so its own files are the only ones locked.

Usage:
    python -m griptape_nodes.updater            # update only
    python -m griptape_nodes.updater --restart  # update and restart the engine
"""

from __future__ import annotations

import argparse
import subprocess

from rich.console import Console

from griptape_nodes.retained_mode.managers.os_manager import OSManager

console = Console()

os_manager = OSManager()


def _parse_args() -> argparse.Namespace:
    """Parse commandline arguments."""
    parser = argparse.ArgumentParser(
        prog="griptape-nodes-updater",
        description="Update griptape-nodes and optionally restart the engine.",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart the engine after updating.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the updater CLI."""
    args = _parse_args()
    _download_and_run_installer()
    if args.restart:
        _restart_engine()
    elif os_manager.is_windows():
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


def _restart_engine() -> None:
    """Restarts the engine."""
    console.print("[bold green]Restarting engine...[/bold green]")
    try:
        os_manager.replace_process(["griptape-nodes", "--no-update"])
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during restart: {e}[/bold red]")


if __name__ == "__main__":
    main()
