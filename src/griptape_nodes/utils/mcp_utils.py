"""MCP (Model Context Protocol) utility functions for Griptape Nodes."""

from griptape.rules import Rule, Ruleset


def create_ruleset_from_rules_string(rules_string: str | None, server_name: str) -> Ruleset | None:
    """Create a Ruleset from a rules string for an MCP server.

    Args:
        rules_string: Optional rules string for the MCP server
        server_name: Name of the MCP server

    Returns:
        Ruleset with a single Rule containing the rules string, or None if rules_string is None/empty
    """
    if not rules_string or not rules_string.strip():
        return None

    rules_text = rules_string.strip()
    ruleset_name = f"mcp_{server_name}_rules"

    return Ruleset(name=ruleset_name, rules=[Rule(rules_text)])

