import asyncio
import contextlib
import json
import logging
import os
import socket
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from fastapi import FastAPI
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    TextContent,
    Tool,
)
from pydantic import TypeAdapter
from starlette.types import Receive, Scope, Send

from griptape_nodes.api_client import Client, RequestClient
from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.events.config_events import (
    GetConfigValueRequest,
    GetWorkspaceRequest,
)
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    DeleteConnectionRequest,
    ListConnectionsForNodeRequest,
)
from griptape_nodes.retained_mode.events.context_events import (
    EnsureWorkflowAndFlowRequest,
    GetWorkflowContextRequest,
    SetWorkflowContextRequest,
)
from griptape_nodes.retained_mode.events.execution_events import (
    ExecuteNodeRequest,
    ResolveNodeRequest,
    StartFlowFromNodeRequest,
    StartFlowRequest,
)
from griptape_nodes.retained_mode.events.flow_events import (
    AutoLayoutFlowRequest,
    CreateFlowRequest,
    DeleteFlowRequest,
    ListFlowsInCurrentContextRequest,
    ListNodesInFlowRequest,
)
from griptape_nodes.retained_mode.events.library_events import (
    DescribeNodeTypeRequest,
    ListCategoriesInLibraryRequest,
    ListNodeTypesInLibraryRequest,
    ListRegisteredLibrariesRequest,
    RegisterSandboxNodeFromSourceRequest,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    DeleteNodeRequest,
    GetNodeMetadataRequest,
    GetNodeResolutionStateRequest,
    ListParametersOnNodeRequest,
    ResetNodeToDefaultsRequest,
    SetLockNodeStateRequest,
    SetNodeMetadataRequest,
)
from griptape_nodes.retained_mode.events.object_events import (
    ClearAllObjectStateRequest,
    RenameObjectRequest,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    GetConnectionsForParameterRequest,
    GetParameterDetailsRequest,
    GetParameterValueRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    ListAllWorkflowsRequest,
    RunWorkflowWithCurrentStateRequest,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

SUPPORTED_REQUEST_EVENTS: dict[str, type[RequestPayload]] = {
    # Workflows
    "RunWorkflowWithCurrentStateRequest": RunWorkflowWithCurrentStateRequest,
    "ListAllWorkflowsRequest": ListAllWorkflowsRequest,
    # Workflow context
    "SetWorkflowContextRequest": SetWorkflowContextRequest,
    "GetWorkflowContextRequest": GetWorkflowContextRequest,
    "EnsureWorkflowAndFlowRequest": EnsureWorkflowAndFlowRequest,
    # Libraries
    "ListRegisteredLibrariesRequest": ListRegisteredLibrariesRequest,
    "ListNodeTypesInLibraryRequest": ListNodeTypesInLibraryRequest,
    "ListCategoriesInLibraryRequest": ListCategoriesInLibraryRequest,
    "RegisterSandboxNodeFromSourceRequest": RegisterSandboxNodeFromSourceRequest,
    "DescribeNodeTypeRequest": DescribeNodeTypeRequest,
    # Configuration
    "GetConfigValueRequest": GetConfigValueRequest,
    "GetWorkspaceRequest": GetWorkspaceRequest,
    # Execution
    "ResolveNodeRequest": ResolveNodeRequest,
    "ExecuteNodeRequest": ExecuteNodeRequest,
    "StartFlowRequest": StartFlowRequest,
    "StartFlowFromNodeRequest": StartFlowFromNodeRequest,
    # Flows
    "CreateFlowRequest": CreateFlowRequest,
    "DeleteFlowRequest": DeleteFlowRequest,
    "ListFlowsInCurrentContextRequest": ListFlowsInCurrentContextRequest,
    # Nodes
    "CreateNodeRequest": CreateNodeRequest,
    "DeleteNodeRequest": DeleteNodeRequest,
    "ListNodesInFlowRequest": ListNodesInFlowRequest,
    "AutoLayoutFlowRequest": AutoLayoutFlowRequest,
    "GetNodeResolutionStateRequest": GetNodeResolutionStateRequest,
    "GetNodeMetadataRequest": GetNodeMetadataRequest,
    "SetNodeMetadataRequest": SetNodeMetadataRequest,
    "ResetNodeToDefaultsRequest": ResetNodeToDefaultsRequest,
    "SetLockNodeStateRequest": SetLockNodeStateRequest,
    # Objects
    "RenameObjectRequest": RenameObjectRequest,
    "ClearAllObjectStateRequest": ClearAllObjectStateRequest,
    # Connections
    "CreateConnectionRequest": CreateConnectionRequest,
    "DeleteConnectionRequest": DeleteConnectionRequest,
    "ListConnectionsForNodeRequest": ListConnectionsForNodeRequest,
    # Parameters
    "ListParametersOnNodeRequest": ListParametersOnNodeRequest,
    "GetParameterValueRequest": GetParameterValueRequest,
    "SetParameterValueRequest": SetParameterValueRequest,
    "GetParameterDetailsRequest": GetParameterDetailsRequest,
    "GetConnectionsForParameterRequest": GetConnectionsForParameterRequest,
}

# Synthetic MCP tool name for the batch envelope. Not a request payload (and so not a member of
# SUPPORTED_REQUEST_EVENTS); the call_tool dispatch special-cases it onto manager.request_batch.
EVENT_REQUEST_BATCH_TOOL_NAME = "EventRequestBatch"
EVENT_REQUEST_BATCH_DESCRIPTION = (
    "Invoke multiple GriptapeNodes single-request tools simultaneously.\n\n"
    "Use this when you already know the sequence of single-request tool calls you want to\n"
    "make (e.g. several CreateNodeRequest + SetParameterValueRequest + CreateConnectionRequest\n"
    "calls in a row), to collapse an N-call build phase down to one round trip. Each inner\n"
    "invocation is dispatched server-side as if it were its own single-request tool call.\n\n"
    "Each entry in `invocations` is `{name: <ToolName>, arguments: <stringified JSON>}`:\n"
    '  * `name` is the bare request type (e.g. "CreateNodeRequest"), NOT the prefixed\n'
    "    MCP tool name (`GriptapeNodes_CreateNodeRequest`). The MCP server prefixes its\n"
    "    tools with `GriptapeNodes_`; for `name` here, drop that prefix.\n"
    "  * `arguments` is a STRING containing the JSON-encoded argument object the matching\n"
    "    single-request tool would accept. The server `json.loads` this string and\n"
    "    validates it against the matching RequestPayload dataclass.\n\n"
    "Concrete example (build a 3-node graph in one batch):\n"
    "{\n"
    '  "invocations": [\n'
    '    {"name": "CreateNodeRequest",\n'
    '     "arguments": "{\\"node_type\\": \\"FluxImageGeneration\\", \\"specific_library_name\\": \\"Griptape Nodes Library\\"}"},\n'
    '    {"name": "SetParameterValueRequest",\n'
    '     "arguments": "{\\"node_name\\": \\"FluxImageGeneration_1\\", \\"parameter_name\\": \\"prompt\\", \\"value\\": \\"a cat\\"}"},\n'
    '    {"name": "CreateConnectionRequest",\n'
    '     "arguments": "{\\"source_node_name\\": \\"FluxImageGeneration_1\\", \\"source_parameter_name\\": \\"output\\", \\"target_node_name\\": \\"DisplayImage_1\\", \\"target_parameter_name\\": \\"image\\"}"}\n'
    "  ]\n"
    "}\n\n"
    "To find the exact field shape for `arguments`, look at the `inputSchema` of the tool\n"
    "named `GriptapeNodes_<name>` in this same MCP toolset. That schema is the authoritative\n"
    "source of truth for required fields, optional fields, types, and defaults.\n\n"
    "Args:\n"
    "    invocations: REQUIRED, non-empty array. Ordered list of inner invocations.\n"
    "        Never call this tool with empty arguments.\n"
    "    timeout_ms: optional. Overall timeout for the whole batch in milliseconds.\n"
    "        Defaults to 30000 ms per inner invocation, capped at 300000 ms.\n\n"
    "Returns:\n"
    "    Ordered list of trimmed responses. Each entry has the same shape as a single-request\n"
    "    tool call ({ok, details, ...payload fields}). Failures appear as\n"
    "    {ok: false, details: ...} in their slot rather than aborting the rest of the batch.\n"
)
# Per-inner-request timeout used when the caller does not pass timeout_ms. Mirrors the timeout the
# single-request path applies (see call_tool below) so a batch of one behaves identically.
_BATCH_PER_REQUEST_TIMEOUT_MS = 30000
# Hard ceiling for an auto-computed batch timeout. Long enough to accommodate a large build phase
# without letting a runaway batch hold the connection open indefinitely.
_BATCH_MAX_AUTO_TIMEOUT_MS = 300000

GTN_MCP_SERVER_HOST = os.getenv("GTN_MCP_SERVER_HOST", "localhost")
# Port of the MCP server (where uvicorn binds). Stable by default so external MCP clients
# (Claude Desktop, Cursor, VS Code, ...) can hard-code the URL in their config files.
# Set to 0 to let the OS assign a free port; set to any other value to pin the port.
GTN_MCP_SERVER_PORT = int(os.getenv("GTN_MCP_SERVER_PORT", "8125"))
GTN_MCP_SERVER_LOG_LEVEL = os.getenv("GTN_MCP_SERVER_LOG_LEVEL", "ERROR").lower()

config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)

mcp_server_logger = logging.getLogger("griptape_nodes_mcp_server")
mcp_server_logger.setLevel(logging.INFO)


def _summarize_result_details(result_details: object) -> str | list[dict] | None:
    """Collapse the engine's nested result_details payload into something terse.

    The engine emits `result_details` as a dict wrapping a list of ResultDetail entries,
    e.g. ``{"result_details": [{"level": 10, "message": "..."}, ...]}``. For the MCP
    surface we only really need the messages, joined on newlines. Anything we do not
    recognize is returned as-is so we never hide information we did not intend to hide.
    """
    if result_details is None:
        return None
    if isinstance(result_details, str):
        return result_details
    if isinstance(result_details, dict):
        inner = result_details.get("result_details")
        if isinstance(inner, list):
            messages = [entry.get("message", "") for entry in inner if isinstance(entry, dict)]
            joined = "\n".join(message for message in messages if message)
            if joined:
                return joined
            return inner
    return result_details  # type: ignore[return-value]


def _trim_response(result: dict) -> dict:
    """Strip envelope noise from an engine response before we hand it back to the MCP client.

    The raw response wraps the real payload in engine/session/routing metadata and an echoed
    request. Agents only need to know whether the call succeeded and the payload fields the
    handler produced, so we surface a success discriminator, a terse `details` string, and the
    rest of the inner `result` object.
    """
    inner = dict(result.get("result") or {})
    result_type = result.get("result_type", "")
    details = _summarize_result_details(inner.pop("result_details", None))

    trimmed: dict = {"ok": result_type.endswith("Success")}
    if details is not None:
        trimmed["details"] = details
    trimmed.update(inner)
    return trimmed


# Synthetic MCP tool name for introspecting the JSON Schema of any tool the server advertises.
# Special-cased in call_tool the same way EventRequestBatch is.
INSPECT_TOOL_SCHEMA_TOOL_NAME = "InspectToolSchema"
INSPECT_TOOL_SCHEMA_DESCRIPTION = (
    "Return the JSON Schema this MCP server advertises for a given tool name.\n\n"
    "Use when: debugging tool-arg generation against a specific LLM, verifying that the schema a\n"
    "client sees matches what the server intends to send (in particular, that nested $ref/$defs\n"
    "resolve correctly), or sanity-checking schema changes without re-running the full agent.\n\n"
    "Args:\n"
    "    tool_name: Name of the tool whose schema you want. Accepts any single-request payload\n"
    "        name (e.g. CreateNodeRequest), the synthetic batch tool name (EventRequestBatch),\n"
    "        or this tool's own name.\n\n"
    "Returns: { tool_name: <name>, schema: <json schema dict> }.\n"
)


# When the model calls EventRequestBatch with no `invocations`, the schema validator no longer
# catches it (we deliberately dropped `required: ["invocations"]` so this hint reaches the model
# instead of MCP SDK's bland "is a required property" message). The text below is what the model
# actually sees as a tool result; keep it agent-actionable, with a working example, and short
# enough that Claude is likely to read it before retrying.
_EMPTY_INVOCATIONS_HINT = (
    "EventRequestBatch was called without any `invocations`. This tool only does something "
    "when you pass an `invocations` array of inner tool calls.\n\n"
    "Each entry MUST be `{name: <ToolName>, arguments: <stringified JSON>}`, where `name` is "
    "the bare request type (e.g. `CreateNodeRequest`, NOT the prefixed `GriptapeNodes_CreateNodeRequest`) "
    "and `arguments` is a JSON-encoded string of that tool's argument object.\n\n"
    "Concrete example (build a Note node and set its text in one batch):\n"
    "{\n"
    '  "invocations": [\n'
    '    {"name": "CreateNodeRequest",\n'
    '     "arguments": "{\\"node_type\\": \\"Note\\", \\"specific_library_name\\": \\"Griptape Nodes Library\\"}"},\n'
    '    {"name": "SetParameterValueRequest",\n'
    '     "arguments": "{\\"node_name\\": \\"Note_1\\", \\"parameter_name\\": \\"note\\", \\"value\\": \\"hello\\"}"}\n'
    "  ]\n"
    "}\n\n"
    "If you do not need to batch multiple calls, call the matching `GriptapeNodes_<RequestName>` "
    "single-request tool directly. Do NOT retry EventRequestBatch with the same empty arguments; "
    "either populate `invocations` or use a different tool."
)


def _event_request_batch_input_schema() -> dict[str, Any]:
    """JSON schema for the synthetic EventRequestBatch tool.

    Mirrors Anthropic's official Claude-cookbook "batch_tool" recipe for parallel tool use
    (https://github.com/anthropics/claude-cookbooks). Each invocation is
    `{name: string, arguments: string}` where `arguments` is a STRINGIFIED JSON object the
    server-side `_build_batch_pairs` parses with `json.loads` before instantiating the
    matching RequestPayload dataclass.

    The string-typed `arguments` field is the load-bearing detail: Anthropic's tool-use
    sampler refuses to populate polymorphic object fields whose shape it can't constrain via
    JSON Schema, but it reliably generates string fields. Treating the inner args as a
    stringified JSON blob bypasses the polymorphic-object problem entirely.
    """
    sorted_request_types = sorted(SUPPORTED_REQUEST_EVENTS)
    return {
        "type": "object",
        "properties": {
            "invocations": {
                "type": "array",
                "description": (
                    "Ordered list of inner invocations. MUST be a non-empty array; calling this "
                    "tool with no `invocations` is a bug. Each entry is "
                    "`{name: <ToolName>, arguments: <stringified JSON>}`."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": sorted_request_types,
                            "description": (
                                "Name of the single-request tool whose handler should run for this entry. "
                                "This is the bare request type (e.g. `CreateNodeRequest`), without the "
                                "`GriptapeNodes_` MCP-tool prefix. Must be one of the names listed in this enum."
                            ),
                        },
                        "arguments": {
                            "type": "string",
                            "description": (
                                "JSON-encoded string of the argument object the tool selected by `name` would accept. "
                                "The server `json.loads` this string and validates it against the matching "
                                "RequestPayload dataclass. Look up the tool whose name is `GriptapeNodes_<name>` "
                                "in this same MCP toolset for the exact properties, required fields, types, "
                                "and defaults to put inside this stringified JSON. "
                                'Examples: when name is "CreateNodeRequest", arguments is '
                                '`"{\\"node_type\\": \\"<NodeType>\\", \\"specific_library_name\\": \\"<Library>\\"}"`; '
                                'when name is "SetParameterValueRequest", arguments is '
                                '`"{\\"node_name\\": \\"<NodeName>\\", \\"parameter_name\\": \\"<ParamName>\\", \\"value\\": <any>}"`. '
                                'For tools that take no fields, pass `"{}"`.'
                            ),
                        },
                    },
                    "required": ["name", "arguments"],
                },
            },
            "timeout_ms": {
                "type": "integer",
                "minimum": 1,
                "description": "Optional. Overall timeout for the batch in milliseconds.",
            },
        },
        # Intentionally NOT requiring `invocations` at the schema level: when the model emits an
        # empty {}, we want our handler to surface `_EMPTY_INVOCATIONS_HINT` (which carries a
        # working example) rather than the MCP SDK's generic "is a required property" string.
    }


def _inspect_tool_schema_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Name of the tool to inspect (e.g. CreateNodeRequest, EventRequestBatch).",
            }
        },
        "required": ["tool_name"],
    }


def _resolve_tool_schema(tool_name: object) -> dict[str, Any]:
    """Return the input schema this server advertises for `tool_name`."""
    if not isinstance(tool_name, str) or not tool_name:
        msg = "Attempted to inspect tool schema. Failed because tool_name must be a non-empty string."
        raise ValueError(msg)
    if tool_name == EVENT_REQUEST_BATCH_TOOL_NAME:
        return _event_request_batch_input_schema()
    if tool_name == INSPECT_TOOL_SCHEMA_TOOL_NAME:
        return _inspect_tool_schema_input_schema()
    if tool_name in SUPPORTED_REQUEST_EVENTS:
        return TypeAdapter(SUPPORTED_REQUEST_EVENTS[tool_name]).json_schema()
    msg = (
        f"Attempted to inspect tool schema for {tool_name!r}. "
        f"Failed because no tool by that name is advertised by this server."
    )
    raise ValueError(msg)


def _build_advertised_tools() -> list[Tool]:
    """Return the full list of MCP Tool objects this server advertises.

    Module-level so `start_mcp_server`'s `list_tools` callback can stay a one-liner.
    """
    single_tools = [
        Tool(name=event.__name__, description=event.__doc__, inputSchema=TypeAdapter(event).json_schema())
        for (_, event) in SUPPORTED_REQUEST_EVENTS.items()
    ]
    batch_tool = Tool(
        name=EVENT_REQUEST_BATCH_TOOL_NAME,
        description=EVENT_REQUEST_BATCH_DESCRIPTION,
        inputSchema=_event_request_batch_input_schema(),
    )
    inspect_tool = Tool(
        name=INSPECT_TOOL_SCHEMA_TOOL_NAME,
        description=INSPECT_TOOL_SCHEMA_DESCRIPTION,
        inputSchema=_inspect_tool_schema_input_schema(),
    )
    return [*single_tools, batch_tool, inspect_tool]


def _build_batch_pairs(raw_invocations: object) -> list[tuple[str, dict[str, Any]]]:
    """Validate the inner invocations array and return (request_type, payload_dict) pairs.

    Each entry is `{name, arguments}` where `arguments` is a stringified JSON object (per
    Anthropic's batch-tool cookbook recipe). We `json.loads` the string, then instantiate the
    matching RequestPayload class so missing required fields and unknown kwargs fail fast
    before anything reaches the wire.
    """
    if raw_invocations is None:
        raise ValueError(_EMPTY_INVOCATIONS_HINT)
    if not isinstance(raw_invocations, list):
        msg = "Attempted to dispatch EventRequestBatch. Failed because 'invocations' must be a list."
        raise TypeError(msg)
    if not raw_invocations:
        raise ValueError(_EMPTY_INVOCATIONS_HINT)

    pairs: list[tuple[str, dict[str, Any]]] = []
    for index, entry in enumerate(raw_invocations):
        if not isinstance(entry, dict):
            msg = f"Attempted to dispatch EventRequestBatch entry {index}. Failed because the entry was not an object."
            raise TypeError(msg)
        name = entry.get("name")
        if not isinstance(name, str) or name not in SUPPORTED_REQUEST_EVENTS:
            msg = (
                f"Attempted to dispatch EventRequestBatch entry {index}. "
                f"Failed because name {name!r} is not a supported tool."
            )
            raise ValueError(msg)
        inner = _parse_batch_arguments(entry.get("arguments", "{}"), index, name)

        payload_cls = SUPPORTED_REQUEST_EVENTS[name]
        try:
            payload_obj = payload_cls(**inner)
        except TypeError as exc:
            msg = (
                f"Attempted to construct {name} for EventRequestBatch entry {index}. "
                f"Failed with arguments {inner!r} because of {exc}."
            )
            raise ValueError(msg) from exc

        pairs.append((name, dict(payload_obj.__dict__)))

    return pairs


def _parse_batch_arguments(raw_arguments: object, index: int, name: str) -> dict[str, Any]:
    """Parse the `arguments` field of a single batch entry into a dict ready for dataclass kwargs.

    Per Anthropic's batch-tool cookbook recipe, `arguments` is a stringified JSON object. Some
    well-behaved clients may send a parsed object instead; we accept either to avoid punishing
    them, but the wire format mandated by the schema is string.
    """
    if isinstance(raw_arguments, str):
        try:
            inner: Any = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError as exc:
            msg = (
                f"Attempted to parse arguments for EventRequestBatch entry {index} ({name}). "
                f"Failed because arguments was not valid JSON: {exc}."
            )
            raise ValueError(msg) from exc
    elif isinstance(raw_arguments, dict):
        inner = raw_arguments
    else:
        msg = (
            f"Attempted to dispatch EventRequestBatch entry {index} ({name}). "
            f"Failed because 'arguments' must be a JSON-encoded string (or object)."
        )
        raise TypeError(msg)
    if not isinstance(inner, dict):
        msg = (
            f"Attempted to dispatch EventRequestBatch entry {index} ({name}). "
            f"Failed because parsed arguments must be a JSON object, got {type(inner).__name__}."
        )
        raise TypeError(msg)
    return inner


def _resolve_batch_timeout_ms(override: object, num_requests: int) -> int:
    """Return the timeout_ms to apply to a batch, validating any caller override.

    Without an override, scales the per-request timeout linearly with batch size and clamps to a
    ceiling so a malformed call cannot hold the connection open indefinitely.
    """
    if override is None:
        return min(_BATCH_PER_REQUEST_TIMEOUT_MS * num_requests, _BATCH_MAX_AUTO_TIMEOUT_MS)
    # bool is a subclass of int; reject explicitly so True does not get treated as 1ms.
    if not isinstance(override, int) or isinstance(override, bool):
        msg = (
            "Attempted to dispatch EventRequestBatch. "
            f"Failed because timeout_ms must be a positive integer, got {override!r}."
        )
        raise TypeError(msg)
    if override <= 0:
        msg = (
            "Attempted to dispatch EventRequestBatch. "
            f"Failed because timeout_ms must be a positive integer, got {override!r}."
        )
        raise ValueError(msg)
    return override


def _trim_batch_results(raw_results: list[Any]) -> list[dict[str, Any]]:
    """Trim each inner response, mapping exceptions returned by request_batch to ok=false slots."""
    trimmed: list[dict[str, Any]] = []
    for raw in raw_results:
        if isinstance(raw, BaseException):
            trimmed.append({"ok": False, "details": str(raw)})
        else:
            trimmed.append(_trim_response(raw))
    return trimmed


def start_mcp_server(api_key: str, sock: socket.socket) -> None:
    """Synchronous version of main entry point for the Griptape Nodes MCP server.

    The socket should already be bound to the desired address and port before calling
    this function. Using a pre-bound socket avoids race conditions when discovering
    the actual port assigned by the OS.
    """
    bound_host, bound_port = sock.getsockname()[:2]
    mcp_server_logger.info("MCP server listening at http://%s:%d/mcp/", bound_host, bound_port)

    app = Server("mcp-gtn")

    # Manager reference to be set in lifespan
    manager: RequestClient | None = None

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return _build_advertised_tools()

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if manager is None:
            msg = "Request manager not initialized"
            raise RuntimeError(msg)

        if name == EVENT_REQUEST_BATCH_TOOL_NAME:
            pairs = _build_batch_pairs(arguments.get("invocations"))
            timeout_ms = _resolve_batch_timeout_ms(arguments.get("timeout_ms"), len(pairs))
            raw_results = await manager.request_batch(pairs, timeout_ms=timeout_ms, return_exceptions=True)
            mcp_server_logger.debug("Got %d batch results", len(raw_results))
            return [TextContent(type="text", text=json.dumps(_trim_batch_results(raw_results)))]

        if name == INSPECT_TOOL_SCHEMA_TOOL_NAME:
            inspected = _resolve_tool_schema(arguments.get("tool_name"))
            payload = {"tool_name": arguments.get("tool_name"), "schema": inspected}
            return [TextContent(type="text", text=json.dumps(payload))]

        if name not in SUPPORTED_REQUEST_EVENTS:
            msg = f"Unsupported tool: {name}"
            raise ValueError(msg)

        request_payload = SUPPORTED_REQUEST_EVENTS[name](**arguments)

        result = await manager.request(
            request_payload.__class__.__name__, dict(request_payload.__dict__), timeout_ms=30000
        )
        mcp_server_logger.debug("Got result: %s", result)

        return [TextContent(type="text", text=json.dumps(_trim_response(result)))]

    # Create the session manager with our app and event store
    session_manager = StreamableHTTPSessionManager(
        app=app,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Context manager for managing session manager and WebSocket client lifecycle."""
        nonlocal manager

        async with Client(api_key=api_key) as ws_client, RequestClient(client=ws_client) as req_manager:
            manager = req_manager
            mcp_server_logger.debug("Request manager initialized")

            async with session_manager.run():
                mcp_server_logger.debug("GTN MCP server started with StreamableHTTP session manager!")
                try:
                    yield
                finally:
                    mcp_server_logger.debug("GTN MCP server shutting down...")
                    manager = None

    mcp_server_app = FastAPI(lifespan=lifespan)

    # ASGI handler for streamable HTTP connections
    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    mcp_server_app.mount("/mcp", app=handle_streamable_http)

    try:
        config = uvicorn.Config(mcp_server_app, log_config=None, log_level=GTN_MCP_SERVER_LOG_LEVEL)
        server = uvicorn.Server(config)
        asyncio.run(server.serve(sockets=[sock]))
    except Exception as e:
        mcp_server_logger.error("MCP server failed: %s", e)
        raise
