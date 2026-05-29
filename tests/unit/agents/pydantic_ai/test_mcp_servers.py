"""Tests for the tolerant MCP server wrapper.

These exercise the blocklist filter and the prefix-stripping logic without
spinning up a real MCP server. We construct a minimal stub that quacks like
an :class:`MCPServer` enough for the wrapper to use.
"""

from __future__ import annotations

from typing import Any, Self

import pytest

from griptape_nodes.agents.pydantic_ai.mcp_servers import _TolerantMCPServer


class _StubMCPServer:
    """The narrow surface of `MCPServer` that `_TolerantMCPServer` actually uses."""

    def __init__(self, *, tool_names: list[str], tool_prefix: str | None) -> None:
        self.tool_prefix = tool_prefix
        self._tool_names = tool_names
        self.id: str | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> bool | None:
        return None

    async def get_tools(self, _ctx: Any) -> dict[str, Any]:
        return {self._full_name(name): object() for name in self._tool_names}

    def _full_name(self, name: str) -> str:
        return f"{self.tool_prefix}_{name}" if self.tool_prefix else name


@pytest.mark.asyncio
async def test_blocklist_filters_named_tool_with_prefix() -> None:
    """A blocklisted tool is dropped from the toolset under the configured prefix."""
    inner = _StubMCPServer(
        tool_names=["EventRequestBatch", "CreateNodeRequest", "ListNodeTypesInLibraryRequest"],
        tool_prefix="GriptapeNodes",
    )
    wrapper = _TolerantMCPServer(
        name="GriptapeNodes",
        inner=inner,  # type: ignore[arg-type]
        tool_blocklist=frozenset({"EventRequestBatch"}),
    )
    async with wrapper:
        tools = await wrapper.get_tools(ctx=None)  # type: ignore[arg-type]
    names = sorted(tools.keys())
    assert names == ["GriptapeNodes_CreateNodeRequest", "GriptapeNodes_ListNodeTypesInLibraryRequest"]


@pytest.mark.asyncio
async def test_blocklist_handles_underscored_tool_names_without_prefix() -> None:
    """Tool names containing underscores are not mangled when no prefix is set."""
    inner = _StubMCPServer(tool_names=["fancy_tool_name", "EventRequestBatch"], tool_prefix=None)
    wrapper = _TolerantMCPServer(
        name="raw",
        inner=inner,  # type: ignore[arg-type]
        tool_blocklist=frozenset({"EventRequestBatch"}),
    )
    async with wrapper:
        tools = await wrapper.get_tools(ctx=None)  # type: ignore[arg-type]
    assert "fancy_tool_name" in tools
    assert "EventRequestBatch" not in tools


@pytest.mark.asyncio
async def test_empty_blocklist_keeps_every_tool() -> None:
    """No blocklist == pass-through."""
    inner = _StubMCPServer(tool_names=["a", "b"], tool_prefix="P")
    wrapper = _TolerantMCPServer(
        name="P",
        inner=inner,  # type: ignore[arg-type]
    )
    async with wrapper:
        tools = await wrapper.get_tools(ctx=None)  # type: ignore[arg-type]
    assert sorted(tools.keys()) == ["P_a", "P_b"]


@pytest.mark.asyncio
async def test_get_tools_returns_empty_when_aenter_failed() -> None:
    """A failed connect drops the toolset to empty rather than blowing up."""

    class _FailingStub(_StubMCPServer):
        async def __aenter__(self) -> Self:
            msg = "connect refused"
            raise RuntimeError(msg)

    inner = _FailingStub(tool_names=["x"], tool_prefix=None)
    wrapper = _TolerantMCPServer(name="x", inner=inner)  # type: ignore[arg-type]
    async with wrapper:
        tools = await wrapper.get_tools(ctx=None)  # type: ignore[arg-type]
    assert tools == {}
