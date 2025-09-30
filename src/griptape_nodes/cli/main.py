"""Main CLI application using typer."""

import sys
from pathlib import Path

import typer
from rich.console import Console

# Add current directory to path for imports to work
sys.path.append(str(Path.cwd()))

from griptape_nodes.cli.commands import config, engine, init, libraries, models, self
from griptape_nodes.cli.commands.engine import _auto_update_self
from griptape_nodes.utils.version_utils import get_complete_version_string

console = Console()

app = typer.Typer(
    name="griptape-nodes",
    help="Griptape Nodes Engine CLI",
    no_args_is_help=False,
    rich_markup_mode="rich",
    invoke_without_command=True,
)

# Add subcommands
app.command("init", help="Initialize engine configuration.")(init.init_command)
app.add_typer(config.app, name="config")
app.add_typer(self.app, name="self")
app.add_typer(libraries.app, name="libraries")
app.add_typer(models.app, name="models")
app.command("engine")(engine.engine_command)


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(  # noqa: FBT001
        False, "--version", help="Show version and exit."
    ),
    no_update: bool = typer.Option(  # noqa: FBT001
        False, "--no-update", help="Skip the auto-update check."
    ),
) -> None:
    """Griptape Nodes Engine CLI."""
    if version:
        version_string = get_complete_version_string()
        console.print(f"[bold green]{version_string}[/bold green]")
        raise typer.Exit

    # Run auto-update check for any command (unless disabled)
    if not no_update:
        _auto_update_self()

    if ctx.invoked_subcommand is None:
        # Default to engine command when no subcommand is specified
        engine.engine_command()


if __name__ == "__main__":
    app()
