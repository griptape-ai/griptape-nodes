# Connect External MCP Clients to Griptape Nodes

Griptape Nodes runs its own MCP server so external agents (Claude Desktop, Claude Code, Cursor, VS Code, etc.) can drive the engine. This page is the inverse of the rest of this section: instead of Griptape Nodes consuming external MCP servers, here we expose Griptape Nodes itself as an MCP server.

## URL

By default the engine listens on:

```
http://localhost:8125/mcp/
```

The trailing slash matters. The transport is **Streamable HTTP**.

When the engine starts, it logs the actual bound address, for example:

```
INFO MCP server listening at http://127.0.0.1:8125/mcp/
```

## Overrides

The host and port are controlled by environment variables:

| Variable                   | Default     | Description                                                              |
| -------------------------- | ----------- | ------------------------------------------------------------------------ |
| `GTN_MCP_SERVER_HOST`      | `localhost` | Interface to bind. Use `127.0.0.1` to be explicit, or `0.0.0.0` for LAN. |
| `GTN_MCP_SERVER_PORT`      | `8125`      | TCP port. Set to `0` to let the OS assign a free port.                   |
| `GTN_MCP_SERVER_LOG_LEVEL` | `ERROR`     | uvicorn log level for the MCP server.                                    |

If the configured port is already in use, the engine falls back to an OS-assigned port. Check the startup log to see the actual URL.

!!! warning "Local-only by default"

    The engine binds to `localhost`, which means only processes on the same machine can reach it. The MCP server has no authentication. Do not bind to `0.0.0.0` or expose the port to the network unless you fully trust everything that can reach it.

## Client configuration

### Claude Code

Add to `~/.claude.json` (or use `claude mcp add`):

```json
{
  "mcpServers": {
    "griptape-nodes": {
      "type": "streamable-http",
      "url": "http://localhost:8125/mcp/"
    }
  }
}
```

### Cursor

Create `~/.cursor/mcp.json` for global access, or `.cursor/mcp.json` in a workspace:

```json
{
  "mcpServers": {
    "griptape-nodes": {
      "url": "http://localhost:8125/mcp/"
    }
  }
}
```

### VS Code

Create `.vscode/mcp.json` in your workspace, or open the user file via **MCP: Open User Configuration**:

```json
{
  "servers": {
    "griptape-nodes": {
      "type": "http",
      "url": "http://localhost:8125/mcp/"
    }
  }
}
```

Note that VS Code uses `servers` (not `mcpServers`) and `"type": "http"`.

### Claude Desktop

Claude Desktop's `claude_desktop_config.json` only supports `stdio` servers. To connect to a remote/HTTP MCP server, either:

- Use **Settings → Connectors → Add custom connector** in the app and paste `http://localhost:8125/mcp/`, or
- Wrap the URL with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) in the config file:

```json
{
  "mcpServers": {
    "griptape-nodes": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8125/mcp/"]
    }
  }
}
```

## Verifying the connection

With the engine running, list the tools the MCP server exposes from the command line:

```bash
npx @modelcontextprotocol/inspector http://localhost:8125/mcp/
```

You should see the engine's request tools (`CreateNodeRequest`, `RunWorkflowWithCurrentStateRequest`, etc.).
