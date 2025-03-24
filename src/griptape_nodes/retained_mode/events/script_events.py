from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class RunScriptFromScratchRequest(RequestPayload):
    file_path: str


@dataclass
@PayloadRegistry.register
class RunScriptFromScratchResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptFromScratchResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptWithCurrentStateRequest(RequestPayload):
    file_path: str


@dataclass
@PayloadRegistry.register
class RunScriptWithCurrentStateResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptWithCurrentStateResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptFromRegistryRequest(RequestPayload):
    script_name: str


@dataclass
@PayloadRegistry.register
class RunScriptFromRegistryResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptFromRegistryResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class RegisterScriptRequest(RequestPayload):
    script_name: str
    file_path: str
    engine_version_created_with: str
    node_libraries_referenced: list[str]
    description: str | None = None
    image: str | None = None


@dataclass
@PayloadRegistry.register
class RegisterScriptResult_Success(ResultPayload_Success):
    script_name: str


@dataclass
@PayloadRegistry.register
class RegisterScriptResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class ListAllScriptsRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ListAllScriptsResult_Success(ResultPayload_Success):
    scripts: dict


@dataclass
@PayloadRegistry.register
class ListAllScriptsResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteScriptRequest(RequestPayload):
    name: str


@dataclass
@PayloadRegistry.register
class DeleteScriptResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class DeleteScriptResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class SaveSceneRequest(RequestPayload):
    file_name: str | None = None


@dataclass
@PayloadRegistry.register
class SaveSceneResult_Success(ResultPayload_Success):
    file_path: str


@dataclass
@PayloadRegistry.register
class SaveSceneResult_Failure(ResultPayload_Failure):
    pass
