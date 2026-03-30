"""Worker subprocess entry point for per-library dependency isolation.

This script is run as a long-lived subprocess using the library's own venv Python.
Library-specific dependencies come from the venv; griptape and griptape_nodes come
from the main griptape-nodes installation via PYTHONPATH injected by the parent process.

IPC protocol: JSON lines over stdin/stdout.

Parent → Worker stdin:
  {"type": "get_all_schemas"}
  {"type": "execute_node", "request_id": "...", "class_name": "...", "node_name": "...", "parameter_values": {...}}
  {"type": "shutdown"}

Worker → Parent stdout:
  {"type": "ready"}
  {"type": "all_schemas", "schemas": {"ClassName": {"base_type": "DataNode", "element_tree": {...}}}}
  {"type": "event", "request_id": "...", "event_class": "...", "payload": {...}}
  {"type": "output", "request_id": "...", "parameter_output_values": {...}}
  {"type": "error", "request_id": "...", "message": "...", "traceback": "..."}
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import io
import json
import logging
import os
import pickle
import sys
import traceback
from argparse import ArgumentParser
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value serialization helpers
# ---------------------------------------------------------------------------


def _serialize_value(value: Any) -> Any:
    """Serialize a value to JSON-safe format, using pickle+base64 for complex types."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return {"__pickled__": base64.b64encode(pickle.dumps(value)).decode()}


def _deserialize_value(value: Any) -> Any:
    """Deserialize a value from JSON-safe format (reversing _serialize_value)."""
    if isinstance(value, dict) and "__pickled__" in value:
        return pickle.loads(base64.b64decode(value["__pickled__"]))  # noqa: S301
    return value


# ---------------------------------------------------------------------------
# Stdout IPC helpers
# ---------------------------------------------------------------------------


def _write_json(msg: dict) -> None:
    """Write a JSON-encoded message to stdout (must already be line-buffered)."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Element tree serialization
# ---------------------------------------------------------------------------


def _get_base_type_name(node_class: type) -> str:
    """Return the most-derived recognized base type name for a node class."""
    from griptape_nodes.exe_types.node_types import ControlNode, DataNode, EndNode, StartNode

    # Check in specificity order: StartNode/EndNode before DataNode/ControlNode
    for name, cls in [
        ("StartNode", StartNode),
        ("EndNode", EndNode),
        ("DataNode", DataNode),
        ("ControlNode", ControlNode),
    ]:
        if issubclass(node_class, cls):
            return name
    return "BaseNode"


def _serialize_element_tree(element: Any) -> dict:
    """Recursively serialize a BaseNodeElement tree to a plain dict.

    For Parameter elements, includes the full parameter schema via to_schema().
    For container elements, includes the element type name and recursively
    serialized children.
    """
    from griptape_nodes.exe_types.core_types import Parameter

    children = [_serialize_element_tree(child) for child in element.children]

    if isinstance(element, Parameter):
        return {
            "element_type": type(element).__name__,
            "name": element.name,
            "param_schema": element.to_schema(),
            "children": children,
        }
    else:
        return {
            "element_type": type(element).__name__,
            "name": element.name,
            "children": children,
        }


# ---------------------------------------------------------------------------
# Event forwarding
# ---------------------------------------------------------------------------


def _forward_event_to_stdout(request_id: str, event: Any) -> None:
    """Serialize an event and write it to stdout for forwarding to the parent process."""
    from griptape_nodes.retained_mode.events.base_events import ExecutionGriptapeNodeEvent, ProgressEvent

    try:
        if isinstance(event, ExecutionGriptapeNodeEvent):
            payload = event.wrapped_event.payload
            if is_dataclass(payload):
                payload_dict = asdict(payload)
            elif hasattr(payload, "__dict__"):
                payload_dict = payload.__dict__
            else:
                return
            _write_json({
                "type": "event",
                "request_id": request_id,
                "event_class": "ExecutionGriptapeNodeEvent",
                "wrapped_event_class": type(payload).__name__,
                "payload": payload_dict,
            })
        elif isinstance(event, ProgressEvent):
            _write_json({
                "type": "event",
                "request_id": request_id,
                "event_class": "ProgressEvent",
                "payload": {
                    "value": _serialize_value(event.value),
                    "node_name": event.node_name,
                    "parameter_name": event.parameter_name,
                },
            })
    except Exception:
        # Never let event forwarding crash execution
        pass


def _install_event_forwarder(request_id: str) -> tuple:
    """Monkey-patch EventManager to forward events to stdout.

    Returns the original (put_event, aput_event) for later restoration.
    """
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    em = GriptapeNodes.EventManager()
    original_put = em.put_event
    original_aput = em.aput_event

    def forwarding_put_event(event: Any) -> None:
        _forward_event_to_stdout(request_id, event)

    async def forwarding_aput_event(event: Any) -> None:
        _forward_event_to_stdout(request_id, event)

    em.put_event = forwarding_put_event  # type: ignore[method-assign]
    em.aput_event = forwarding_aput_event  # type: ignore[method-assign]
    return original_put, original_aput


def _uninstall_event_forwarder(original_put: Any, original_aput: Any) -> None:
    """Restore the original EventManager put_event and aput_event."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    em = GriptapeNodes.EventManager()
    em.put_event = original_put  # type: ignore[method-assign]
    em.aput_event = original_aput  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Node class loading
# ---------------------------------------------------------------------------


def _load_node_classes(library_json_path: Path) -> dict[str, type]:
    """Load all node classes declared in the library JSON file.

    Returns a mapping of class_name -> node class for all successfully loaded classes.
    """
    from griptape_nodes.node_library.library_registry import LibrarySchema

    base_dir = library_json_path.parent

    with library_json_path.open() as f:
        raw = json.load(f)
    library_data = LibrarySchema.model_validate(raw)

    # Make the library's base directory importable so relative imports in nodes work
    base_dir_str = str(base_dir)
    if base_dir_str not in sys.path:
        sys.path.insert(0, base_dir_str)

    node_classes: dict[str, type] = {}
    for node_def in library_data.nodes:
        node_file_path = base_dir / node_def.file_path
        module_name = f"_worker_node_{node_def.class_name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, node_file_path)
            if spec is None or spec.loader is None:
                logger.error("Could not load spec for %s from %s", node_def.class_name, node_file_path)
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            node_class = getattr(module, node_def.class_name)
            node_classes[node_def.class_name] = node_class
        except Exception:
            logger.exception("Failed to load node class %s from %s", node_def.class_name, node_file_path)

    return node_classes


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------


def handle_get_all_schemas(node_classes: dict[str, type]) -> None:
    """Build schemas from each node class by instantiating it, then send to parent."""
    schemas: dict[str, dict] = {}
    for class_name, node_class in node_classes.items():
        try:
            node = node_class(name=f"__schema_{class_name}")
            schemas[class_name] = {
                "base_type": _get_base_type_name(node_class),
                "element_tree": _serialize_element_tree(node.root_ui_element),
            }
        except Exception as e:
            schemas[class_name] = {"error": str(e), "traceback": traceback.format_exc()}
    _write_json({"type": "all_schemas", "schemas": schemas})


def handle_execute_node(msg: dict, node_classes: dict[str, type]) -> None:
    """Instantiate and execute a node, streaming events and returning output values."""
    request_id = msg["request_id"]
    class_name = msg["class_name"]
    node_name = msg["node_name"]
    parameter_values = msg.get("parameter_values", {})

    if class_name not in node_classes:
        _write_json({
            "type": "error",
            "request_id": request_id,
            "message": f"Unknown node class: {class_name!r}",
            "traceback": "",
        })
        return

    try:
        node = node_classes[class_name](name=node_name)
    except Exception as e:
        _write_json({
            "type": "error",
            "request_id": request_id,
            "message": f"Failed to instantiate {class_name}: {e}",
            "traceback": traceback.format_exc(),
        })
        return

    # Populate parameter values sent from the parent process
    for param_name, raw_value in parameter_values.items():
        node.parameter_values[param_name] = _deserialize_value(raw_value)

    # Forward all events emitted during execution to the parent process
    original_put, original_aput = _install_event_forwarder(request_id)
    try:
        asyncio.run(node.aprocess())
    except Exception as e:
        _write_json({
            "type": "error",
            "request_id": request_id,
            "message": str(e),
            "traceback": traceback.format_exc(),
        })
        return
    finally:
        _uninstall_event_forwarder(original_put, original_aput)

    outputs = {
        param_name: _serialize_value(value)
        for param_name, value in node.parameter_output_values.items()
    }
    _write_json({"type": "output", "request_id": request_id, "parameter_output_values": outputs})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    # The main griptape-nodes venv's site-packages are passed via this env var
    # so that griptape_nodes's own dependencies (semver, anyio, pydantic, etc.)
    # are importable. They are appended — not prepended — so library-specific
    # packages from this venv keep priority for conflict isolation.
    _fallback = os.environ.get("GRIPTAPE_NODES_MAIN_SITE_PACKAGES", "")
    for _p in _fallback.split(os.pathsep):
        if _p and _p not in sys.path:
            sys.path.append(_p)

    # Make stdout line-buffered so each JSON message flushes immediately.
    # stdin stays in its default (line) mode since we read it line by line.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, line_buffering=True)

    # Route all logging to stderr so it never corrupts the stdout IPC channel
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

    parser = ArgumentParser(description="Griptape Nodes library worker subprocess")
    parser.add_argument(
        "--library-json-path",
        required=True,
        help="Path to the library JSON definition file",
    )
    args = parser.parse_args()

    # Initialize the GriptapeNodes singleton so node code can access managers
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    GriptapeNodes()

    # Load node classes before signalling ready
    try:
        node_classes = _load_node_classes(Path(args.library_json_path))
    except Exception:
        logger.exception("Failed to load node classes from %s", args.library_json_path)
        sys.exit(1)

    # Signal to parent that the worker is ready to receive messages
    _write_json({"type": "ready"})

    # Main message loop: read one JSON line per message from parent
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError:
            logger.error("Worker received malformed JSON: %r", raw_line)
            continue

        msg_type = msg.get("type")

        if msg_type == "get_all_schemas":
            handle_get_all_schemas(node_classes)
        elif msg_type == "execute_node":
            handle_execute_node(msg, node_classes)
        elif msg_type == "shutdown":
            break
        else:
            logger.warning("Worker received unknown message type: %r", msg_type)


if __name__ == "__main__":
    _main()
