from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.events.arbitrary_python_events import (
    RunArbitraryPythonStringRequest,
    RunArbitraryPythonStringResultFailure,
    RunArbitraryPythonStringResultSuccess,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager


class ArbitraryCodeExecManager:
    def __init__(self, event_manager: EventManager) -> None:
        event_manager.assign_manager_to_request_type(
            RunArbitraryPythonStringRequest, self.on_run_arbitrary_python_string_request
        )

    def on_run_arbitrary_python_string_request(self, request: RunArbitraryPythonStringRequest) -> ResultPayload:
        try:
            string_buffer = io.StringIO()
            with redirect_stdout(string_buffer):
                python_output = exec(request.python_string)  # noqa: S102

            captured_output = string_buffer.getvalue()
            result = RunArbitraryPythonStringResultSuccess(python_output=captured_output)
        except Exception as e:
            python_output = f"ERROR: {e}"
            result = RunArbitraryPythonStringResultFailure(python_output=python_output)

        return result
