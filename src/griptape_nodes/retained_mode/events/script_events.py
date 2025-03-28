from dataclasses import dataclass

from griptape_nodes.node_library.script_registry import LibraryNameAndVersion
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class RunScriptFromScratchRequest(RequestPayload):
    file_path: str


@dataclass
@PayloadRegistry.register
class RunScriptFromScratchResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptFromScratchResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptWithCurrentStateRequest(RequestPayload):
    file_path: str


@dataclass
@PayloadRegistry.register
class RunScriptWithCurrentStateResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptWithCurrentStateResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptFromRegistryRequest(RequestPayload):
    script_name: str


@dataclass
@PayloadRegistry.register
class RunScriptFromRegistryResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class RunScriptFromRegistryResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RegisterScriptRequest(RequestPayload):
    script_name: str
    file_path: str
    engine_version_created_with: str
    node_libraries_referenced: list[LibraryNameAndVersion]
    description: str | None = None
    image: str | None = None


@dataclass
@PayloadRegistry.register
class RegisterScriptResultSuccess(ResultPayloadSuccess):
    script_name: str


@dataclass
@PayloadRegistry.register
class RegisterScriptResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListAllScriptsRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ListAllScriptsResultSuccess(ResultPayloadSuccess):
    scripts: dict


@dataclass
@PayloadRegistry.register
class ListAllScriptsResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteScriptRequest(RequestPayload):
    name: str


@dataclass
@PayloadRegistry.register
class DeleteScriptResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteScriptResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SaveSceneRequest(RequestPayload):
    file_name: str | None = None


@dataclass
@PayloadRegistry.register
class SaveSceneResultSuccess(ResultPayloadSuccess):
    file_path: str


@dataclass
@PayloadRegistry.register
class SaveSceneResultFailure(ResultPayloadFailure):
    pass
