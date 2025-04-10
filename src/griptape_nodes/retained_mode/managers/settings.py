from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    TomlConfigSettingsSource,
    YamlConfigSettingsSource,
)
from xdg_base_dirs import xdg_config_dirs, xdg_config_home, xdg_data_home


def _find_config_files(filename: str, extension: str) -> list[Path]:
    config_files = []

    # Recursively search parent directories up to HOME
    current_path = Path.cwd()
    while current_path not in (Path.home(), current_path.parent) and current_path != current_path.parent:
        config_files.append(current_path / f"{filename}.{extension}")
        current_path = current_path.parent

    # Search `GriptapeNodes/` inside current working directory (this is the implicit default)
    config_files.append(Path.cwd() / "GriptapeNodes" / f"{filename}.{extension}")

    # Search XDG_CONFIG_HOME (e.g., `~/.config/griptape_nodes/griptape_nodes_config.yaml`)
    config_files.append(xdg_config_home() / "griptape_nodes" / f"{filename}.{extension}")

    # Search XDG_CONFIG_DIRS (e.g., `/etc/xdg/griptape_nodes/gt_nodes.yaml`)
    config_files.extend([Path(xdg_dir) / "griptape_nodes" / f"{filename}.{extension}" for xdg_dir in xdg_config_dirs()])

    # Reverse the list so that the most specific paths are checked first
    config_files.reverse()

    return config_files


@dataclass
class WorkflowSettingsDetail:
    """Griptape-provided workflows are pathed differently and display in the GUI in a different section."""

    file_name: str
    is_griptape_provided: bool


class AppInitializationComplete(BaseModel):
    libraries_to_register: list[str] = Field(
        default_factory=lambda: [str(xdg_data_home() / "griptape_nodes/nodes/griptape_nodes_library.json")]
    )
    workflows_to_register: list[WorkflowSettingsDetail] = Field(
        default_factory=lambda: []  # noqa: PIE807 (leaving as a lambda for list for when we are ready to re-populate)
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
        ]
    )


class Settings(BaseSettings):
    workspace_directory: str = Field(default=str(Path().cwd() / "GriptapeNodes"))
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

    class Config:
        json_file = _find_config_files("griptape_nodes_config", "json")
        toml_file = _find_config_files("griptape_nodes_config", "toml")
        yaml_file = _find_config_files("griptape_nodes_config", "yaml")
        extra = "allow"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            JsonConfigSettingsSource(settings_cls),
            YamlConfigSettingsSource(settings_cls),
            TomlConfigSettingsSource(settings_cls),
        )
