"""Send requests to a running Griptape Nodes engine via WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import importlib
import inspect
import json
import pkgutil
import sys
import uuid
from os import getenv
from typing import Any

import typer
from dotenv.main import DotEnv
from xdg_base_dirs import xdg_config_home

from griptape_nodes.api_client.client import Client, get_default_websocket_url

app = typer.Typer(help="Send requests to a running Griptape Nodes engine.")

_ENV_VAR_PATH = xdg_config_home() / "griptape_nodes" / ".env"

_HEARTBEAT_INTERVAL_SECONDS = 5
_TERMINAL_EVENT_TYPES = frozenset({"ControlFlowResolvedEvent", "ControlFlowCancelledEvent"})


def _get_api_key() -> str | None:
    """Resolve the API key from the environment or dotenv file."""
    api_key = getenv("GT_CLOUD_API_KEY")
    if api_key is not None:
        return api_key
    return DotEnv(_ENV_VAR_PATH).get("GT_CLOUD_API_KEY")


def _resolve_topics(engine_id: str | None, session_id: str | None) -> tuple[str, str]:
    """Determine request and response topics from the provided IDs.

    Returns:
        A (request_topic, response_topic) tuple.
    """
    if session_id is not None:
        return f"sessions/{session_id}/request", f"sessions/{session_id}/response"
    if engine_id is not None:
        return f"engines/{engine_id}/request", f"engines/{engine_id}/response"
    return "request", "response"


def _print_json(data: Any) -> None:
    """Write JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))  # noqa: T201


def _print_error(message: str) -> None:
    """Write a JSON error object to stderr and raise SystemExit."""
    print(json.dumps({"error": message}), file=sys.stderr)  # noqa: T201
    raise typer.Exit(code=1)


def _populate_payload_registry() -> None:
    """Import all event modules to populate the PayloadRegistry.

    Some modules may fail to import due to incomplete Pydantic model definitions
    when loaded outside the full engine context. These are skipped silently.
    """
    import griptape_nodes.retained_mode.events as events_pkg

    for module_info in pkgutil.iter_modules(events_pkg.__path__):
        with contextlib.suppress(Exception):
            importlib.import_module(f"griptape_nodes.retained_mode.events.{module_info.name}")


async def _send_request(  # noqa: PLR0913
    api_key: str,
    request_type: str,
    payload: dict[str, Any],
    request_topic: str,
    response_topic: str,
    timeout_ms: int,
) -> dict[str, Any]:
    """Connect, send a single request, wait for the response, then disconnect."""
    from griptape_nodes.api_client.request_client import RequestClient

    client = Client(api_key=api_key, url=get_default_websocket_url())
    async with client:
        request_client = RequestClient(
            client,
            request_topic_fn=lambda: request_topic,
            response_topic_fn=lambda: response_topic,
        )
        async with request_client:
            return await request_client.request(request_type, payload, timeout_ms=timeout_ms)


async def _send_request_and_watch(
    api_key: str,
    request_type: str,
    payload: dict[str, Any],
    session_id: str,
    timeout_ms: int,
) -> None:
    """Send a request and stream execution events until the flow completes.

    Uses Client directly instead of RequestClient so that execution_event
    messages are not consumed and dropped by the response listener. The timeout
    applies to receiving the first response. After that, we stream indefinitely
    until a terminal execution event.
    """
    request_topic = f"sessions/{session_id}/request"
    response_topic = f"sessions/{session_id}/response"

    request_id = str(uuid.uuid4())

    client = Client(api_key=api_key, url=get_default_websocket_url())
    async with client:
        await client.subscribe("response")
        await client.subscribe(response_topic)

        event_payload: dict[str, Any] = {
            "event_type": "EventRequest",
            "request_type": request_type,
            "request_id": request_id,
            "request": payload,
            "response_topic": response_topic,
        }
        await client.publish("EventRequest", event_payload, request_topic)

        async def _send_heartbeats() -> None:
            while True:
                await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
                hb_payload: dict[str, Any] = {
                    "event_type": "EventRequest",
                    "request_type": "SessionHeartbeatRequest",
                    "request": {"request_id": str(uuid.uuid4())},
                    "response_topic": response_topic,
                }
                await client.publish("EventRequest", hb_payload, request_topic)

        heartbeat_task = asyncio.create_task(_send_heartbeats())
        timeout_sec = timeout_ms / 1000

        try:
            # Phase 1: wait for initial response with timeout.
            deadline = asyncio.get_event_loop().time() + timeout_sec
            async for message in client.messages:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    _print_error(f"Timed out waiting for response to {request_type} after {timeout_ms}ms.")
                    return

                msg_type = message.get("type")
                msg_payload = message.get("payload", {})

                if msg_type in ("success_result", "failure_result") and msg_payload.get("request_type") == request_type:
                    if msg_type == "failure_result":
                        _print_json(msg_payload)
                        raise typer.Exit(code=1)
                    _print_json(msg_payload.get("result", {}))
                    break

            # Phase 2: stream execution events until terminal event.
            async for message in client.messages:
                msg_type = message.get("type")
                msg_payload = message.get("payload", {})

                if msg_type == "execution_event":
                    _print_json(msg_payload)
                    payload_type = msg_payload.get("payload_type", "")
                    if payload_type in _TERMINAL_EVENT_TYPES:
                        return
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task


_SKIP_FIELDS = frozenset({"broadcast_result", "failure_log_level"})
_SKIP_RESULT_FIELDS = frozenset({"result_details", "altered_workflow_state"})


def _get_class_info(cls: type, skip_fields: frozenset[str]) -> dict[str, Any]:
    """Extract description and field info from a dataclass."""
    info: dict[str, Any] = {}
    if cls.__doc__:
        info["description"] = inspect.cleandoc(cls.__doc__)

    if dataclasses.is_dataclass(cls):
        fields = {}
        for field in dataclasses.fields(cls):
            if field.name in skip_fields:
                continue
            field_info: dict[str, str] = {"type": str(field.type)}
            if field.default is not dataclasses.MISSING:
                field_info["default"] = str(field.default)
            fields[field.name] = field_info
        if fields:
            info["fields"] = fields

    return info


def _get_populated_registry() -> dict[str, type]:
    """Populate and return the PayloadRegistry."""
    import logging

    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

    logging.disable(logging.CRITICAL)
    _populate_payload_registry()
    logging.disable(logging.NOTSET)
    return PayloadRegistry.get_registry()


def _find_result_class(base_name: str, suffix: str, registry: dict[str, type]) -> type | None:
    """Find a result class by trying common naming patterns."""
    patterns = [
        f"{base_name}Result{suffix}",
        f"{base_name}{suffix}",
        f"{base_name}_Result{suffix}",
        f"{base_name}Result_{suffix}",
        f"{base_name}_{suffix}",
    ]
    for pattern in patterns:
        if pattern in registry:
            return registry[pattern]
    return None


@app.command("list")
def list_command() -> None:
    """List all available request types with their fields and documentation."""
    from griptape_nodes.retained_mode.events.base_events import RequestPayload

    registry = _get_populated_registry()

    request_types: dict[str, Any] = {}
    for name, cls in sorted(registry.items()):
        if not (inspect.isclass(cls) and issubclass(cls, RequestPayload) and cls != RequestPayload):
            continue
        request_types[name] = _get_class_info(cls, _SKIP_FIELDS)

    _print_json(request_types)


@app.command("describe")
def describe_command(
    request_type: str = typer.Argument(help="The request type name (e.g. EngineHeartbeatRequest)."),
) -> None:
    """Show full details for a request type, including its success and failure result classes."""
    from griptape_nodes.retained_mode.events.base_events import RequestPayload

    registry = _get_populated_registry()

    cls = registry.get(request_type)
    if cls is None or not (inspect.isclass(cls) and issubclass(cls, RequestPayload)):
        _print_error(f"Unknown request type: {request_type}. Use 'gtn request list' to see available types.")

    result: dict[str, Any] = {"request": _get_class_info(cls, _SKIP_FIELDS)}  # type: ignore[arg-type]

    # Find result classes using the same heuristic as EngineNode
    base_name = request_type.removesuffix("Request") if request_type.endswith("Request") else request_type

    success_cls = _find_result_class(base_name, "Success", registry)
    if success_cls is not None:
        result["success_result"] = _get_class_info(success_cls, _SKIP_RESULT_FIELDS)

    failure_cls = _find_result_class(base_name, "Failure", registry)
    if failure_cls is not None:
        result["failure_result"] = _get_class_info(failure_cls, _SKIP_RESULT_FIELDS)

    _print_json(result)


@app.command("send")
def send_command(  # noqa: PLR0913
    request_type: str = typer.Argument(help="The request type name (e.g. EngineHeartbeatRequest)."),
    payload: str = typer.Option("{}", "--payload", "-p", help="JSON string for request fields."),
    engine_id: str | None = typer.Option(
        None, "--engine-id", "-e", help="Target engine ID (sets engine-scoped topics)."
    ),
    session_id: str | None = typer.Option(
        None, "--session-id", "-s", help="Target session ID (sets session-scoped topics)."
    ),
    timeout: int = typer.Option(30000, "--timeout", "-t", help="Timeout in milliseconds for the response."),
    watch: bool = typer.Option(  # noqa: FBT001
        False, "--watch", "-w", help="Stream execution events after the initial response (requires --session-id)."
    ),
) -> None:
    """Send a request to a running Griptape Nodes engine and print the response as JSON."""
    api_key = _get_api_key()
    if api_key is None:
        _print_error("No API key found. Set GT_CLOUD_API_KEY in your environment or run: gtn init --api-key <key>")

    try:
        request_payload = json.loads(payload)
    except json.JSONDecodeError as e:
        _print_error(f"Invalid JSON in --payload: {e}")
        return  # unreachable, _print_error raises

    if watch and session_id is None:
        _print_error("--watch requires --session-id.")
        return

    if watch:
        try:
            asyncio.run(
                _send_request_and_watch(
                    api_key=api_key,  # type: ignore[arg-type]
                    request_type=request_type,
                    payload=request_payload,
                    session_id=session_id,  # type: ignore[arg-type]
                    timeout_ms=timeout,
                )
            )
        except Exception as e:
            _print_error(str(e))
        return

    request_topic, response_topic = _resolve_topics(engine_id, session_id)

    try:
        result = asyncio.run(
            _send_request(
                api_key=api_key,  # type: ignore[arg-type]
                request_type=request_type,
                payload=request_payload,
                request_topic=request_topic,
                response_topic=response_topic,
                timeout_ms=timeout,
            )
        )
    except TimeoutError:
        _print_error(f"Timed out waiting for response to {request_type} after {timeout}ms.")
    except ConnectionError as e:
        _print_error(f"WebSocket connection failed: {e}")
    except Exception as e:
        _print_error(str(e))
    else:
        _print_json(result)
