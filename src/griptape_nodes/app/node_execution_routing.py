from __future__ import annotations

from typing import TYPE_CHECKING, cast

from griptape_nodes.retained_mode.events.base_events import EventRequest
from griptape_nodes.retained_mode.events.execution_events import (
    ExecuteNodeRequest,
    ExecuteNodeResultFailure,
    ExecuteNodeResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.app.worker_manager import WorkerManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager


def _deserialize_execute_node_result(
    payload: dict,
) -> ExecuteNodeResultSuccess | ExecuteNodeResultFailure:
    """Reconstruct an ExecuteNodeResultSuccess or ExecuteNodeResultFailure from a raw payload dict."""
    result_type = payload.get("result_type", "")
    result_data = payload.get("result", {})
    try:
        if result_type == ExecuteNodeResultSuccess.__name__:
            return ExecuteNodeResultSuccess(**result_data)
        if result_type == ExecuteNodeResultFailure.__name__:
            return ExecuteNodeResultFailure(**result_data)
    except TypeError as e:
        msg = f"Failed to deserialize execute-node result (result_type={result_type!r}): {e}"
        raise ValueError(msg) from e
    msg = f"Unrecognized execute-node result_type: {result_type!r}"
    raise ValueError(msg)


def setup(worker_manager: WorkerManager, event_manager: EventManager, *, is_worker: bool = False) -> None:
    """Register the ExecuteNodeRequest handler.

    node_executor.py always dispatches ExecuteNodeRequest through the event system.

    In orchestrator mode this handler routes to a library-specific worker process when
    one is registered, and falls back to NodeManager.on_execute_node_request for local
    execution. In worker mode the node is always executed locally — the worker IS the
    target, so no further routing is needed.
    """
    if is_worker:

        async def _local_execute_node(
            request: ExecuteNodeRequest,
        ) -> ExecuteNodeResultSuccess | ExecuteNodeResultFailure:
            return cast(
                "ExecuteNodeResultSuccess | ExecuteNodeResultFailure",
                await GriptapeNodes.NodeManager().on_execute_node_request(request),
            )

        event_manager.assign_manager_to_request_type(ExecuteNodeRequest, _local_execute_node)
        return

    async def _routed_execute_node(
        request: ExecuteNodeRequest,
    ) -> ExecuteNodeResultSuccess | ExecuteNodeResultFailure:
        worker = worker_manager.get_worker_for_library(request.library_name) if request.library_name else None

        if worker is None:
            library_info = (
                GriptapeNodes.LibraryManager().get_library_info_by_library_name(request.library_name)
                if request.library_name
                else None
            )
            if library_info is not None and library_info.requires_worker:
                msg = (
                    f"Library '{request.library_name}' requires a dedicated worker process "
                    "that is not yet registered. The worker may still be starting up."
                )
                raise RuntimeError(msg)
            # No worker registered for this library — execute locally.
            return cast(
                "ExecuteNodeResultSuccess | ExecuteNodeResultFailure",
                await GriptapeNodes.NodeManager().on_execute_node_request(request),
            )

        worker_engine_id, worker_request_topic = worker
        raw = await worker_manager.route_to_worker(
            EventRequest(request=request),
            worker_engine_id,
            worker_request_topic,
        )
        return _deserialize_execute_node_result(raw)

    event_manager.assign_manager_to_request_type(ExecuteNodeRequest, _routed_execute_node)
