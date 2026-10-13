"""Agent harnesses that drive coding-agent CLIs installed on the user's computer.

:data:`CLI_HARNESSES` maps each CLI provider type in the provider catalog to the
harness that runs it.
"""

from griptape_nodes.agents.cli.base import CliHarness, CliHarnessError
from griptape_nodes.agents.cli.claude_code import ClaudeCodeHarness
from griptape_nodes.agents.cli.codex import CodexHarness
from griptape_nodes.agents.cli.gemini_cli import GeminiCliHarness
from griptape_nodes.agents.cli.opencode import OpenCodeHarness
from griptape_nodes.agents.cli.pi import PiHarness

CLI_HARNESSES: dict[str, type[CliHarness]] = {
    harness.harness_id: harness
    for harness in (ClaudeCodeHarness, CodexHarness, PiHarness, GeminiCliHarness, OpenCodeHarness)
}

__all__ = ["CLI_HARNESSES", "CliHarness", "CliHarnessError"]
