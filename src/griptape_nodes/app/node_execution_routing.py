from __future__ import annotations

from typing import TYPE_CHECKING

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


def setup(worker_manager: WorkerManager, event_manager: EventManager) -> None:
    """Register the ExecuteNodeRequest handler with worker routing.

    node_executor.py always dispatches ExecuteNodeRequest through the event system.
    This handler routes to a worker when one is registered, and falls back to
    NodeManager.on_execute_node_request for local execution.
    """

    async def _routed_execute_node(
        request: ExecuteNodeRequest,
    ) -> ExecuteNodeResultSuccess | ExecuteNodeResultFailure:
        worker = worker_manager.get_active_worker()
        if worker is None:
            # No worker registered — execute locally.
            return await GriptapeNodes.NodeManager().on_execute_node_request(request)

        worker_engine_id, worker_request_topic = worker
        raw = await worker_manager.route_to_worker(
            EventRequest(request=request),
            worker_engine_id,
            worker_request_topic,
        )
        return _deserialize_execute_node_result(raw)

    event_manager.assign_manager_to_request_type(ExecuteNodeRequest, _routed_execute_node)
