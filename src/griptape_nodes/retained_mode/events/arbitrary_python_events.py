from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

# Eyes open about this one, yessir.
# THIS IS CONFIGURABLE BEHAVIOR. CUSTOMERS NOT WISHING TO ENABLE IT CAN DISABLE IT.
# NO FUNCTION-CRITICAL RELIANCE ON THESE EVENTS.


@dataclass
@PayloadRegistry.register
class RunArbitraryPythonStringRequest(RequestPayload):
    """Execute arbitrary Python code string.

    Use when: Development/debugging, testing code snippets, prototyping,
    educational purposes. WARNING: This is configurable behavior that can be disabled.

    Args:
        python_string: Python code string to execute

    Results: RunArbitraryPythonStringResultSuccess (with output) | RunArbitraryPythonStringResultFailure (execution error)
    """

    python_string: str


@dataclass
@PayloadRegistry.register
class RunArbitraryPythonStringResultSuccess(ResultPayloadSuccess):
    """Python code executed successfully.

    Args:
        python_output: String output from the executed Python code
    """

    python_output: str


@dataclass
@PayloadRegistry.register
class RunArbitraryPythonStringResultFailure(ResultPayloadFailure):
    """Python code execution failed.

    Args:
        python_output: Error output from the failed Python code execution
    """

    python_output: str
