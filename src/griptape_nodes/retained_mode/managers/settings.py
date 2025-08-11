from pathlib import Path
from typing import Any, Literal

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
    nodes: dict[str, Any] = Field(
        default_factory=lambda: {
            "Griptape": {"GT_CLOUD_API_KEY": "$GT_CLOUD_API_KEY"},
            "OpenAI": {"OPENAI_API_KEY": "$OPENAI_API_KEY"},
            "Amazon": {
                "AWS_ACCESS_KEY_ID": "$AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY": "$AWS_SECRET_ACCESS_KEY",
                "AWS_DEFAULT_REGION": "$AWS_DEFAULT_REGION",
                "AMAZON_OPENSEARCH_HOST": "$AMAZON_OPENSEARCH_HOST",
                "AMAZON_OPENSEARCH_INDEX_NAME": "$AMAZON_OPENSEARCH_INDEX_NAME",
            },
            "Anthropic": {"ANTHROPIC_API_KEY": "$ANTHROPIC_API_KEY"},
            "BlackForest Labs": {"BFL_API_KEY": "$BFL_API_KEY"},
            "Microsoft Azure": {
                "AZURE_OPENAI_ENDPOINT": "$AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_DALL_E_3_ENDPOINT": "$AZURE_OPENAI_DALL_E_3_ENDPOINT",
                "AZURE_OPENAI_DALL_E_3_API_KEY": "$AZURE_OPENAI_DALL_E_3_API_KEY",
                "AZURE_OPENAI_API_KEY": "$AZURE_OPENAI_API_KEY",
            },
            "Cohere": {"COHERE_API_KEY": "$COHERE_API_KEY"},
            "Eleven Labs": {"ELEVEN_LABS_API_KEY": "$ELEVEN_LABS_API_KEY"},
            "Exa": {"EXA_API_KEY": "$EXA_API_KEY"},
            "Grok": {"GROK_API_KEY": "$GROK_API_KEY"},
            "Groq": {"GROQ_API_KEY": "$GROQ_API_KEY"},
            "Google": {"GOOGLE_API_KEY": "$GOOGLE_API_KEY", "GOOGLE_API_SEARCH_ID": "$GOOGLE_API_SEARCH_ID"},
            "Huggingface": {"HUGGINGFACE_HUB_ACCESS_TOKEN": "$HUGGINGFACE_HUB_ACCESS_TOKEN"},
            "LeonardoAI": {"LEONARDO_API_KEY": "$LEONARDO_API_KEY"},
            "Pinecone": {
                "PINECONE_API_KEY": "$PINECONE_API_KEY",
                "PINECONE_ENVIRONMENT": "$PINECONE_ENVIRONMENT",
                "PINECONE_INDEX_NAME": "$PINECONE_INDEX_NAME",
            },
            "Tavily": {"TAVILY_API_KEY": "$TAVILY_API_KEY"},
            "Serper": {"SERPER_API_KEY": "$SERPER_API_KEY"},
        }
    )
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
