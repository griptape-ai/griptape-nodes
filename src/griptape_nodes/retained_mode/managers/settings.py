from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppInitializationComplete(BaseModel):
    libraries_to_register: list[str] = Field(default_factory=list)
    workflows_to_register: list[str] = Field(default_factory=list)


class AppEvents(BaseModel):
    on_app_initialization_complete: AppInitializationComplete = Field(default_factory=AppInitializationComplete)
    events_to_echo_as_retained_mode: list[str] = Field(
        default_factory=lambda: [
            "CreateConnectionRequest",
            "DeleteConnectionRequest",
            "CreateFlowRequest",
            "DeleteFlowRequest",
            "CreateNodeRequest",
            "DeleteNodeRequest",
            "AddParameterToNodeRequest",
            "RemoveParameterFromNodeRequest",
            "SetParameterValueRequest",
            "AlterParameterDetailsRequest",
            "SetConfigValueRequest",
            "SetConfigCategoryRequest",
            "DeleteWorkflowRequest",
            "ResolveNodeRequest",
            "StartFlowRequest",
            "CancelFlowRequest",
            "UnresolveFlowRequest",
            "SingleExecutionStepRequest",
            "SingleNodeStepRequest",
            "ContinueExecutionStepRequest",
            "SetLockNodeStateRequest",
        ]
    )


class Settings(BaseModel):
    model_config = ConfigDict(extra="allow")

    workspace_directory: str = Field(default=str(Path().cwd() / "GriptapeNodes"))
    static_files_directory: str = Field(
        default="staticfiles",
        description="Path to the static files directory, relative to the workspace directory.",
    )
    sandbox_library_directory: str = Field(
        default="sandbox_library",
        description="Path to the sandbox library directory (useful while developing nodes). If presented as just a directory (e.g., 'sandbox_library') it will be interpreted as being relative to the workspace directory.",
    )
    app_events: AppEvents = Field(default_factory=AppEvents)
    log_level: str = Field(default="INFO")
    storage_backend: Literal["local", "gtc"] = Field(default="local")
    minimum_disk_space_gb_libraries: float = Field(
        default=10.0,
        description="Minimum disk space in GB required for library installation and virtual environment operations",
    )
    minimum_disk_space_gb_workflows: float = Field(
        default=1.0, description="Minimum disk space in GB required for saving workflows"
    )
    synced_workflows_directory: str = Field(
        default="synced_workflows",
        description="Path to the synced workflows directory, relative to the workspace directory.",
    )
