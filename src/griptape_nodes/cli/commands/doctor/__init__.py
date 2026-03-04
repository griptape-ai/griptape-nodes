"""Doctor command for Griptape Nodes CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from rich.table import Table

from griptape_nodes.cli.commands.doctor.websocket_connection import WebSocketConnectionCheck

if TYPE_CHECKING:
    from griptape_nodes.cli.commands.doctor.base import HealthCheck
from griptape_nodes.cli.shared import console


def doctor_command() -> None:
    """Run health checks on the Griptape Nodes engine."""
    checks: list[HealthCheck] = [
        WebSocketConnectionCheck(),
    ]

    results = [check.run() for check in checks]

    table = Table(title="Griptape Nodes Health Checks")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    all_passed = True
    for result in results:
        if result.passed:
            status = "[bold green]PASS[/bold green]"
        else:
            status = "[bold red]FAIL[/bold red]"
            all_passed = False
        table.add_row(result.name, status, result.message)

    console.print(table)

    if not all_passed:
        raise typer.Exit(code=1)
