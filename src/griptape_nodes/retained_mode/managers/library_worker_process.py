"""Manages the long-lived worker subprocess for a single library.

Provides IPC with the worker via JSON lines over stdin/stdout, and builds stub
node classes from worker-provided schemas for use in the main process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to the worker entry point script
_WORKER_ENTRY_PATH = Path(__file__).parent.parent.parent / "bootstrap" / "workers" / "library_worker_entry.py"

# How long to wait for the worker to write {"type": "ready"} before giving up
_STARTUP_TIMEOUT_SECONDS = 120

# How long to wait for the worker to exit cleanly before killing it
_SHUTDOWN_TIMEOUT_SECONDS = 5.0

# asyncio StreamReader buffer limit for worker stdout; must be large enough to hold
# a single all_schemas JSON line (one line per library, can be several hundred KB)
_STDOUT_STREAM_LIMIT_BYTES = 4 * 1024 * 1024  # 4 MB


class LibraryWorkerProcess:
    """Manages a single long-lived worker subprocess for one library.

    The worker runs with the library's venv Python so its dependencies are
    isolated from the main process. IPC uses JSON lines over stdin/stdout.
    """

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        # Maps request_id → Future that resolves when the worker responds
        self._pending: dict[str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self._ready_event: asyncio.Event = asyncio.Event()

    def is_running(self) -> bool:
        """Return True if the subprocess is alive."""
        return self._process is not None and self._process.returncode is None

    async def start(
        self,
        library_json_path: Path,
        venv_python: Path,
        core_pythonpath: str,
        main_site_packages: str = "",
    ) -> None:
        """Launch the worker subprocess and wait until it signals ready.

        Args:
            library_json_path: Path to the library JSON definition file.
            venv_python: Path to the library venv's Python executable.
            core_pythonpath: PYTHONPATH string pointing to the main griptape/griptape_nodes packages.
            main_site_packages: Pathsep-joined list of the main venv's site-packages directories.
                Passed to the worker as a fallback so griptape_nodes's own runtime dependencies
                (semver, anyio, pydantic, etc.) are importable. The worker appends these rather
                than prepending them so library-specific packages retain priority.
        """
        env = os.environ.copy()
        # Prepend the core package paths so the worker always uses griptape and
        # griptape_nodes from the main installation, never from the library venv.
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = core_pythonpath + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        env["PYTHONUNBUFFERED"] = "1"
        if main_site_packages:
            env["GRIPTAPE_NODES_MAIN_SITE_PACKAGES"] = main_site_packages

        self._process = await asyncio.create_subprocess_exec(
            str(venv_python),
            str(_WORKER_ENTRY_PATH),
            "--library-json-path",
            str(library_json_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=_STDOUT_STREAM_LIMIT_BYTES,
        )

        self._reader_task = asyncio.create_task(self._read_loop())

        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=_STARTUP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            await self.stop()
            msg = (
                f"Worker subprocess for {library_json_path} did not become ready "
                f"within {_STARTUP_TIMEOUT_SECONDS}s"
            )
            raise RuntimeError(msg) from None

    async def _read_loop(self) -> None:
        """Read worker stdout line by line, dispatching messages to pending futures."""
        assert self._process is not None
        assert self._process.stdout is not None

        try:
            async for raw_line in self._process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Worker sent non-JSON stdout line: %r", line)
                    continue

                msg_type = msg.get("type")

                if msg_type == "ready":
                    self._ready_event.set()

                elif msg_type == "all_schemas":
                    request_id = msg.get("request_id", "__get_all_schemas__")
                    future = self._pending.pop(request_id, None)
                    if future is not None and not future.done():
                        future.set_result(msg.get("schemas", {}))

                elif msg_type == "event":
                    self._forward_event(
                        event_class=msg.get("event_class", ""),
                        payload_dict=msg.get("payload", {}),
                        raw_msg=msg,
                    )

                elif msg_type == "output":
                    request_id = msg.get("request_id", "")
                    future = self._pending.pop(request_id, None)
                    if future is not None and not future.done():
                        future.set_result(msg.get("parameter_output_values", {}))

                elif msg_type == "error":
                    request_id = msg.get("request_id", "")
                    future = self._pending.pop(request_id, None)
                    if future is not None and not future.done():
                        error_msg = msg.get("message", "Unknown worker error")
                        tb = msg.get("traceback", "")
                        future.set_exception(RuntimeError(f"{error_msg}\n{tb}".strip()))

                else:
                    logger.debug("Worker sent unknown message type: %r", msg_type)

        except Exception:
            logger.debug("Worker _read_loop ended", exc_info=True)

        finally:
            # Process has exited or stdout closed — fail all pending futures.
            error = RuntimeError("Worker process exited unexpectedly")
            for future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

            # Drain and log stderr — use error level so crashes are visible
            if self._process is not None and self._process.stderr is not None:
                try:
                    stderr_data = await self._process.stderr.read()
                    if stderr_data:
                        logger.error("Worker stderr: %s", stderr_data.decode("utf-8", errors="replace"))
                except Exception:
                    pass

    def _forward_event(self, event_class: str, payload_dict: dict, raw_msg: dict) -> None:
        """Reconstruct an event from a worker message and put it into the main event queue."""
        from griptape_nodes.retained_mode.events.base_events import (
            ExecutionEvent,
            ExecutionGriptapeNodeEvent,
            ProgressEvent,
        )
        from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        try:
            if event_class == "ExecutionGriptapeNodeEvent":
                wrapped_event_class_name = raw_msg.get("wrapped_event_class", "")
                payload_type = PayloadRegistry.get_type(wrapped_event_class_name)
                if payload_type is None:
                    return

                # Reconstruct the payload dataclass, ignoring unknown fields
                if is_dataclass(payload_type):
                    known_field_names = {f.name for f in fields(payload_type)}
                    filtered = {k: v for k, v in payload_dict.items() if k in known_field_names}
                    reconstructed = payload_type(**filtered)
                else:
                    reconstructed = payload_type(**payload_dict)

                event = ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=reconstructed))
                GriptapeNodes.EventManager().put_event(event)

            elif event_class == "ProgressEvent":
                event = ProgressEvent(
                    value=payload_dict.get("value"),
                    node_name=payload_dict.get("node_name", ""),
                    parameter_name=payload_dict.get("parameter_name", ""),
                )
                GriptapeNodes.EventManager().put_event(event)

        except Exception:
            logger.debug("Failed to forward worker event %r", event_class, exc_info=True)

    async def _write_message(self, msg: dict) -> None:
        """Write a JSON message to the worker stdin (serialized via lock)."""
        assert self._process is not None
        assert self._process.stdin is not None

        line = json.dumps(msg) + "\n"
        async with self._write_lock:
            self._process.stdin.write(line.encode("utf-8"))
            await self._process.stdin.drain()

    def _make_future(self, request_id: str) -> asyncio.Future:
        """Register and return a new Future for the given request_id."""
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future
        return future

    async def get_all_schemas(self) -> dict[str, dict]:
        """Request schemas for all node classes from the worker."""
        request_id = "__get_all_schemas__"
        future = self._make_future(request_id)
        await self._write_message({"type": "get_all_schemas"})
        return await future

    async def execute_node(
        self,
        class_name: str,
        node_name: str,
        parameter_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a node in the worker, forwarding events to the main process in real time.

        Returns the parameter_output_values dict from the worker.
        """
        request_id = str(uuid.uuid4())
        future = self._make_future(request_id)
        await self._write_message({
            "type": "execute_node",
            "request_id": request_id,
            "class_name": class_name,
            "node_name": node_name,
            "parameter_values": parameter_values,
        })
        return await future

    async def stop(self) -> None:
        """Shut down the worker subprocess gracefully, killing it if necessary."""
        if self._process is not None and self._process.returncode is None:
            try:
                await self._write_message({"type": "shutdown"})
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._process.wait(), timeout=_SHUTDOWN_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                self._process.kill()

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        self._process = None
        self._reader_task = None

    async def fetch_and_build_stubs(self) -> dict[str, type]:
        """Fetch node schemas from the worker and return a dict of stub node classes.

        Nodes whose schemas contain an "error" key are skipped.
        """
        schemas = await self.get_all_schemas()
        return {
            class_name: _build_stub_class(class_name, schema)
            for class_name, schema in schemas.items()
            if "error" not in schema
        }


# ---------------------------------------------------------------------------
# Stub class factory (module-level so stubs can be pickled by class reference)
# ---------------------------------------------------------------------------


def _populate_from_element_tree(node: Any, element_tree: dict) -> None:
    """Walk a serialized element tree and add Parameter elements to the node.

    Recurses into nested containers (e.g., ParameterGroup) to collect all
    parameters in document order.
    """
    from griptape_nodes.exe_types.core_types import Parameter

    for child in element_tree.get("children", []):
        param_schema = child.get("param_schema")
        if param_schema is not None:
            try:
                param = Parameter.from_schema(param_schema)
                node.add_parameter(param)
            except Exception:
                logger.debug(
                    "Failed to reconstruct parameter %r from schema",
                    child.get("name"),
                    exc_info=True,
                )

        # Recurse into nested element containers
        nested_children = child.get("children", [])
        if nested_children:
            _populate_from_element_tree(node, child)


def _build_stub_class(class_name: str, schema: dict) -> type:
    """Build a stub BaseNode subclass from a worker-provided node schema.

    The stub's __init__ reconstructs parameters from the schema so the node
    can participate in connection validation and UI rendering in the main
    process. Actual execution is dispatched to the worker.
    """
    from griptape_nodes.exe_types.node_types import BaseNode, ControlNode, DataNode, EndNode, StartNode

    base_type_map: dict[str, type] = {
        "DataNode": DataNode,
        "ControlNode": ControlNode,
        "StartNode": StartNode,
        "EndNode": EndNode,
        "BaseNode": BaseNode,
    }
    base_class: type = base_type_map.get(schema.get("base_type", "DataNode"), DataNode)
    element_tree: dict = schema.get("element_tree", {"children": []})

    def __init__(self, name: str, metadata: Any = None) -> None:
        base_class.__init__(self, name, metadata)
        _populate_from_element_tree(self, element_tree)

    def process(self) -> None:
        raise NotImplementedError(
            f"Stub {class_name}: execution is dispatched to the library worker subprocess"
        )

    stub = type(class_name, (base_class,), {"__init__": __init__, "process": process})
    stub.__module__ = f"griptape_nodes.node_libraries.stub.{class_name}"
    return stub
