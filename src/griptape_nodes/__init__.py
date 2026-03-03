"""Griptape Nodes package."""

import sys
from pathlib import Path

from rich.console import Console


def main() -> None:
    """Main entry point for the Griptape Nodes CLI."""
    # Hack to make paths "just work". # noqa: FIX004
    # Without this, packages like `nodes` don't properly import.
    # Long term solution could be to make `nodes` a proper src-layout package
    # but current engine relies on importing files rather than packages.
    sys.path.append(str(Path.cwd()))

    console = Console()
    with console.status("[bold green]Loading Griptape Nodes...", spinner="dots"):
        from griptape_nodes.cli.main import app

    app()


__all__ = ["main"]
