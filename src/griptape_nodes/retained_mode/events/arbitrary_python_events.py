from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

# Eyes open about this one, yessir.
# THIS IS CONFIGURABLE BEHAVIOR. CUSTOMERS NOT WISHING TO ENABLE IT CAN DISABLE IT.
# NO FUNCTION-CRITICAL RELIANCE ON THESE EVENTS.


@dataclass
@PayloadRegistry.register
class RunArbitraryPythonStringRequest(RequestPayload):
    python_string: str


@dataclass
@PayloadRegistry.register
class RunArbitraryPythonStringResult_Success(ResultPayload_Success):
    python_output: str


@dataclass
@PayloadRegistry.register
class RunArbitraryPythonStringResult_Failure(ResultPayload_Failure):
    python_output: str
