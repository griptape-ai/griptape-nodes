from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as PydanticField


class Category(BaseModel):
    """A category with name and optional description."""

    name: str
    description: str | None = None

    def __str__(self) -> str:
        return self.name


# Predefined categories to avoid repetition
FILE_SYSTEM = Category(name="File System", description="Directories and file paths for the application")
APPLICATION_EVENTS = Category(name="Application Events", description="Configuration for application lifecycle events")
API_KEYS = Category(name="API Keys", description="API keys and authentication credentials")
EXECUTION = Category(name="Execution", description="Workflow execution and processing settings")
STORAGE = Category(name="Storage", description="Data storage and persistence configuration")
SYSTEM_REQUIREMENTS = Category(name="System Requirements", description="System resource requirements and limits")
MCP_SERVERS = Category(name="MCP Servers", description="Model Context Protocol server configurations")
PROJECTS = Category(name="Projects", description="Project template configurations and registrations")


def Field(category: str | Category = "General", **kwargs) -> Any:
    """Enhanced Field with default category that can be overridden."""
    if "json_schema_extra" not in kwargs:
        # Convert Category to dict or use string directly
        if isinstance(category, Category):
            category_dict = {"name": category.name}
            if category.description:
                category_dict["description"] = category.description
            kwargs["json_schema_extra"] = {"category": category_dict}
        else:
            kwargs["json_schema_extra"] = {"category": category}
    return PydanticField(**kwargs)


class WorkflowExecutionMode(StrEnum):
    """Execution type for node processing."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class LogLevel(StrEnum):
    """Logging level for the application."""

    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    name: str = Field(description="Unique name/identifier for the MCP server")
    enabled: bool = Field(default=True, description="Whether this MCP server is enabled")
    transport: str = Field(default="stdio", description="Transport type: stdio, sse, streamable_http, or websocket")

    # StdioConnection fields
    command: str | None = Field(default=None, description="Command to start the MCP server (required for stdio)")
    args: list[str] = Field(default_factory=list, description="Arguments to pass to the MCP server command (stdio)")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables for the MCP server (stdio)")
    cwd: str | None = Field(default=None, description="Working directory for the MCP server (stdio)")
    encoding: str = Field(default="utf-8", description="Text encoding for stdio communication")
    encoding_error_handler: str = Field(default="strict", description="Encoding error handler for stdio")

    # HTTP-based connection fields (sse, streamable_http, websocket)
    url: str | None = Field(
        default=None, description="URL for HTTP-based connections (sse, streamable_http, websocket)"
    )
    headers: dict[str, str] | None = Field(default=None, description="HTTP headers for HTTP-based connections")
    timeout: float | None = Field(default=None, description="HTTP timeout in seconds")
    sse_read_timeout: float | None = Field(default=None, description="SSE read timeout in seconds")
    terminate_on_close: bool = Field(
        default=True, description="Whether to terminate session on close (streamable_http)"
    )

    # Common fields
    description: str | None = Field(default=None, description="Optional description of what this MCP server provides")
    capabilities: list[str] = Field(default_factory=list, description="List of capabilities this MCP server provides")

    def __str__(self) -> str:
        return f"{self.name} ({'enabled' if self.enabled else 'disabled'})"


class AppInitializationComplete(BaseModel):
    libraries_to_register: list[str] = Field(default_factory=list)
    workflows_to_register: list[str] = Field(default_factory=list)
    secrets_to_register: list[str] = Field(
        default_factory=lambda: ["HF_TOKEN", "GT_CLOUD_API_KEY"],
        description="Core secrets to register in the secrets manager. Library-specific secrets are registered automatically from library settings.",
    )
    models_to_download: list[str] = Field(default_factory=list)
    projects_to_register: list[str] = Field(
        category=PROJECTS,
        default_factory=list,
        description="List of project.yml file paths to load at startup",
    )


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

    workspace_directory: str = Field(
        category=FILE_SYSTEM,
        default=str(Path().cwd() / "GriptapeNodes"),
    )
    static_files_directory: str = Field(
        category=FILE_SYSTEM,
        default="staticfiles",
        description="Path to the static files directory, relative to the workspace directory.",
    )
    sandbox_library_directory: str = Field(
        category=FILE_SYSTEM,
        default="sandbox_library",
        description="Path to the sandbox library directory (useful while developing nodes). If presented as just a directory (e.g., 'sandbox_library') it will be interpreted as being relative to the workspace directory.",
    )
    app_events: AppEvents = Field(
        category=APPLICATION_EVENTS,
        default_factory=AppEvents,
    )
    log_level: LogLevel = Field(category=EXECUTION, default=LogLevel.INFO)
    workflow_execution_mode: WorkflowExecutionMode = Field(
        category=EXECUTION,
        default=WorkflowExecutionMode.SEQUENTIAL,
        description="Workflow execution mode for node processing",
    )

    @field_validator("workflow_execution_mode", mode="before")
    @classmethod
    def validate_workflow_execution_mode(cls, v: Any) -> WorkflowExecutionMode:
        """Convert string values to WorkflowExecutionMode enum."""
        if isinstance(v, str):
            try:
                return WorkflowExecutionMode(v.lower())
            except ValueError:
                # Return default if invalid string
                return WorkflowExecutionMode.SEQUENTIAL
        elif isinstance(v, WorkflowExecutionMode):
            return v
        else:
            # Return default for any other type
            return WorkflowExecutionMode.SEQUENTIAL

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: Any) -> LogLevel:
        """Convert string values to LogLevel enum."""
        if isinstance(v, str):
            try:
                return LogLevel(v.upper())
            except ValueError:
                # Return default if invalid string
                return LogLevel.INFO
        elif isinstance(v, LogLevel):
            return v
        else:
            # Return default for any other type
            return LogLevel.INFO

    max_nodes_in_parallel: int | None = Field(
        category=EXECUTION,
        default=5,
        description="Maximum number of nodes executing at a time for parallel execution.",
    )
    storage_backend: Literal["local", "gtc"] = Field(category=STORAGE, default="local")
    minimum_disk_space_gb_libraries: float = Field(
        category=SYSTEM_REQUIREMENTS,
        default=10.0,
        description="Minimum disk space in GB required for library installation and virtual environment operations",
    )
    minimum_disk_space_gb_workflows: float = Field(
        category=SYSTEM_REQUIREMENTS,
        default=1.0,
        description="Minimum disk space in GB required for saving workflows",
    )
    synced_workflows_directory: str = Field(
        category=FILE_SYSTEM,
        default="synced_workflows",
        description="Path to the synced workflows directory, relative to the workspace directory.",
    )
    thread_storage_backend: Literal["local", "gtc"] = Field(
        category=STORAGE,
        default="local",
        description="Storage backend for conversation threads: 'local' for filesystem or 'gtc' for Griptape Cloud",
    )
    enable_workspace_file_watching: bool = Field(
        category=FILE_SYSTEM,
        default=True,
        description="Enable file watching for synced workflows directory",
    )
    mcp_servers: list[MCPServerConfig] = Field(
        category=MCP_SERVERS,
        default_factory=list,
        description="List of Model Context Protocol server configurations",
    )
