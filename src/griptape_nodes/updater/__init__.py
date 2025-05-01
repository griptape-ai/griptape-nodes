"""Runs *outside* the main process, so its own files are the only ones locked.

Usage:
    python -m griptape_nodes.updater            # update only
    python -m griptape_nodes.updater --restart  # update and restart the engine
"""

from __future__ import annotations

import argparse
import subprocess

from rich.console import Console

console = Console()


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
        subprocess.run(  # noqa: S603
            ["griptape-nodes"],  # noqa: S607
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during restart: {e}[/bold red]")


if __name__ == "__main__":
    main()
