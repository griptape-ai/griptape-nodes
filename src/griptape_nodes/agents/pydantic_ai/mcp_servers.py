"""Build Pydantic AI :class:`MCPServer` toolsets from engine MCP configs.

The engine speaks ``MCPServerConfig`` (a TypedDict with a ``transport`` plus
transport-specific fields). Pydantic AI exposes one class per transport
(:class:`MCPServerStdio`, :class:`MCPServerSSE`, :class:`MCPServerStreamableHTTP`).
This module is the bridge.

It also wraps each server in a :class:`_TolerantMCPServer` that swallows
connection errors during ``__aenter__``/``list_tools``: a single broken MCP
server should never bring down the whole agent run. The agent will simply
have an empty tool set from that server until the next reconnect attempt.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Self

from pydantic_ai.mcp import MCPServer, MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP
from pydantic_ai.toolsets import AbstractToolset

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic_ai._run_context import RunContext


logger = logging.getLogger("griptape_nodes")


DEFAULT_TOOL_MAX_RETRIES = 3
"""How many times Pydantic AI retries a single MCP tool call after a `ModelRetry`.

The Pydantic AI default is 1, which is too tight: when an LLM (especially Claude)
fumbles the args for a tool with a structured `list[dict]` parameter, it usually
gets a validation error, sees the retry message, and corrects on the second
attempt. With `max_retries=1` that second attempt is the last one, so a single
schema misunderstanding kills the whole run.
"""

DEFAULT_GTN_TOOL_BLOCKLIST: frozenset[str] = frozenset()
"""GTN MCP tools the chat-sidebar agent never sees.

Left empty by default; the wrapper supports arbitrary blocklists for callers
that want to hide specific tools (e.g. tests, alternate harnesses).
"""


def mcp_server_from_config(name: str, config: Mapping[str, Any]) -> AbstractToolset[Any] | None:  # noqa: PLR0911
    """Build a Pydantic AI MCP toolset from an engine ``MCPServerConfig``.

    Returns ``None`` and logs a warning when the config is missing required
    fields for its declared transport. The returned toolset is wrapped in a
    tolerant adapter that downgrades connect / discovery failures to log
    warnings instead of letting them blow up the agent run.
    """
    transport = config.get("transport", "stdio")

    if transport == "stdio":
        command = config.get("command")
        if not command:
            logger.warning("MCP server %r: stdio transport requires `command`; skipping.", name)
            return None
        return _wrap(
            name,
            MCPServerStdio(
                command=command,
                args=list(config.get("args") or []),
                env=config.get("env"),
                cwd=config.get("cwd"),
                tool_prefix=name,
                max_retries=DEFAULT_TOOL_MAX_RETRIES,
            ),
        )

    if transport == "sse":
        url = config.get("url")
        if not url:
            logger.warning("MCP server %r: sse transport requires `url`; skipping.", name)
            return None
        return _wrap(
            name,
            MCPServerSSE(
                url=url,
                headers=dict(config.get("headers") or {}),
                timeout=float(config.get("timeout") or 5),
                tool_prefix=name,
                max_retries=DEFAULT_TOOL_MAX_RETRIES,
            ),
        )

    if transport in ("streamable_http", "websocket"):
        url = config.get("url")
        if not url:
            logger.warning("MCP server %r: %s transport requires `url`; skipping.", name, transport)
            return None
        return _wrap(
            name,
            MCPServerStreamableHTTP(
                url=url,
                headers=dict(config.get("headers") or {}),
                timeout=float(config.get("timeout") or 5),
                tool_prefix=name,
                max_retries=DEFAULT_TOOL_MAX_RETRIES,
            ),
        )

    logger.warning("MCP server %r: unsupported transport %r; skipping.", name, transport)
    return None


def streamable_http_local(url: str, *, name: str | None = None) -> AbstractToolset[Any]:
    """Convenience builder for the engine's own MCP server (streamable HTTP)."""
    return _wrap(
        name or "GriptapeNodes",
        MCPServerStreamableHTTP(url=url, tool_prefix=name, max_retries=DEFAULT_TOOL_MAX_RETRIES),
        tool_blocklist=DEFAULT_GTN_TOOL_BLOCKLIST,
    )


def _wrap(name: str, server: MCPServer, *, tool_blocklist: frozenset[str] = frozenset()) -> AbstractToolset[Any]:
    return _TolerantMCPServer(name=name, inner=server, tool_blocklist=tool_blocklist)


class _TolerantMCPServer(AbstractToolset[Any]):
    """Adapter that makes an MCP server fault-tolerant.

    If ``__aenter__`` raises, the adapter logs and proceeds with an empty
    toolset for this run. ``list_tools``/``call_tool`` failures are surfaced
    as ordinary exceptions (they're per-tool errors, the framework already
    reports them sensibly).

    The wrapper is intentionally minimal: it only forwards the methods the
    agent toolset machinery actually uses, and forwards everything else via
    ``__getattr__`` so future Pydantic AI changes don't silently break us.
    """

    def __init__(
        self,
        *,
        name: str,
        inner: MCPServer,
        tool_blocklist: frozenset[str] = frozenset(),
        tool_prefix: str | None = None,
    ) -> None:
        self._inner = inner
        self._mcp_name = name
        self._connected = False
        self._tool_blocklist = tool_blocklist
        self._tool_prefix = tool_prefix

    @property
    def id(self) -> str | None:
        return self._inner.id

    @property
    def label(self) -> str:
        return f"mcp:{self._mcp_name}"

    async def __aenter__(self) -> Self:
        try:
            await self._inner.__aenter__()
            self._connected = True
            logger.info("MCP server %r: connected.", self._mcp_name)
        except Exception as exc:
            self._connected = False
            logger.warning(
                "MCP server %r: failed to connect (%s). Agent will run without its tools.",
                self._mcp_name,
                exc,
            )
        return self

    async def __aexit__(self, *exc_info: object) -> bool | None:
        if not self._connected:
            return None
        with suppress(Exception):
            return await self._inner.__aexit__(*exc_info)
        return None

    async def get_tools(self, ctx: RunContext[Any]) -> dict[str, Any]:
        if not self._connected:
            return {}
        try:
            tools = await self._inner.get_tools(ctx)
        except Exception as exc:
            logger.warning(
                "MCP server %r: get_tools failed (%s). Returning empty tool set.",
                self._mcp_name,
                exc,
            )
            return {}
        if not self._tool_blocklist:
            return tools
        return {
            full_name: tool
            for full_name, tool in tools.items()
            if self._bare_name(full_name) not in self._tool_blocklist
        }

    async def call_tool(self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any], tool: Any) -> Any:
        if not self._connected:
            msg = f"MCP server {self._mcp_name!r} is not connected"
            raise RuntimeError(msg)
        return await self._inner.call_tool(name, tool_args, ctx, tool)

    def __getattr__(self, item: str) -> Any:
        # Forward anything else to the wrapped server. Done in __getattr__ so
        # explicit attributes above (e.g. `id`) take precedence on lookup.
        return getattr(self._inner, item)

    def _bare_name(self, full_name: str) -> str:
        """Strip the configured Pydantic AI tool prefix off a discovered tool name.

        Pydantic AI prepends ``tool_prefix + '_'`` to every tool name when a
        prefix is set. We only strip that exact prefix; tools whose underlying
        names happen to contain underscores stay intact.
        """
        if self._tool_prefix:
            head = f"{self._tool_prefix}_"
            if full_name.startswith(head):
                return full_name[len(head) :]
        return full_name
