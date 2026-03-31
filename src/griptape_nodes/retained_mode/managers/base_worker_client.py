"""Abstract base class for a library worker client.

A worker client encapsulates the communication channel to the process (or remote
service) that executes library node code in an isolated environment. Concrete
implementations supply the transport; this ABC defines the interface used by the
rest of the engine.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseWorkerClient(ABC):
    """Interface for a library worker — an isolated execution environment for one library.

    Concrete implementations choose the transport (stdin/stdout subprocess, WebSocket,
    in-process mock, etc.) while callers (library_manager, node_executor) depend only
    on this interface.

    Note: start() is intentionally excluded. Different transports have fundamentally
    different setup requirements (subprocess params, URL + credentials, in-process args,
    etc.), so startup is the responsibility of each concrete class.
    """

    @abstractmethod
    def is_running(self) -> bool:
        """Return True if the worker is alive and ready to accept requests."""

    @abstractmethod
    async def stop(self) -> None:
        """Shut down the worker gracefully."""

    @abstractmethod
    async def get_all_schemas(self) -> dict[str, dict]:
        """Request schemas for all node classes from the worker.

        Returns a mapping of class_name → schema dict. Schemas may contain an
        "error" key if the worker failed to build the schema for that class.
        """

    @abstractmethod
    async def execute_node(
        self,
        class_name: str,
        node_name: str,
        parameter_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a node in the worker and return its parameter_output_values."""

    async def fetch_and_build_stubs(self) -> dict[str, type]:
        """Fetch node schemas from the worker and return stub node classes.

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

    def _init(self: Any, name: str, metadata: Any = None) -> None:
        base_class.__init__(self, name, metadata)
        _populate_from_element_tree(self, element_tree)

    def process(self: Any) -> None:
        library = getattr(self.__class__, "_worker_library_name", "<unknown library>")
        msg = (
            f"Stub node '{class_name}' (library '{library}') must only be executed via its "
            f"library worker subprocess. Direct in-process execution is forbidden. "
            f"This is a fatal bug — the node executor must route this node to its worker."
        )
        raise RuntimeError(msg)

    stub = type(class_name, (base_class,), {"__init__": _init, "process": process})
    stub.__module__ = f"griptape_nodes.node_libraries.stub.{class_name}"
    return stub
