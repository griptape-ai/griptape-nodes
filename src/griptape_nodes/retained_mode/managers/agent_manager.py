import logging

from griptape.artifacts import ErrorArtifact
from griptape.drivers import GriptapeCloudPromptDriver
from griptape.memory.structure import ConversationMemory
from griptape.tasks import PromptTask

from griptape_nodes.retained_mode.events.agent_events import (
    ConfigureAgentConversationMemoryRequest,
    ConfigureAgentConversationMemoryResultFailure,
    ConfigureAgentConversationMemoryResultSuccess,
    ConfigureAgentPromptDriverRequest,
    ConfigureAgentPromptDriverResultFailure,
    ConfigureAgentPromptDriverResultSuccess,
    GetConversationMemoryRequest,
    GetConversationMemoryResultFailure,
    GetConversationMemoryResultSuccess,
    RunAgentRequest,
    RunAgentResultFailure,
    RunAgentResultSuccess,
)
from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

logger = logging.getLogger("griptape_nodes")

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"

config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)


class AgentManager:
    def __init__(self, event_manager: EventManager | None = None) -> None:
        self.conversation_memory = ConversationMemory()
        api_key = secrets_manager.get_secret(API_KEY_ENV_VAR)
        if not api_key:
            msg = f"Secret '{API_KEY_ENV_VAR}' not found"
            raise ValueError(msg)
        self.prompt_driver = GriptapeCloudPromptDriver(api_key=api_key)

        if event_manager is not None:
            event_manager.assign_manager_to_request_type(RunAgentRequest, self.on_handle_run_agent_request)
            event_manager.assign_manager_to_request_type(
                ConfigureAgentPromptDriverRequest, self.on_handle_configure_agent_prompt_driver_request
            )
            event_manager.assign_manager_to_request_type(
                ConfigureAgentConversationMemoryRequest, self.on_handle_configure_agent_conversation_memory_request
            )
            event_manager.assign_manager_to_request_type(
                GetConversationMemoryRequest, self.on_handle_get_conversation_memory_request
            )

    def on_handle_run_agent_request(self, request: RunAgentRequest) -> ResultPayload:
        task_output = PromptTask(
            request.input, prompt_driver=self.prompt_driver, conversation_memory=self.conversation_memory
        ).run()
        if isinstance(task_output, ErrorArtifact):
            details = f"Error running agent: {task_output.value}"
            logger.error(details)
            return RunAgentResultFailure(error=task_output.to_json())
        return RunAgentResultSuccess(output=task_output.to_json())

    def on_handle_configure_agent_prompt_driver_request(
        self, request: ConfigureAgentPromptDriverRequest
    ) -> ResultPayload:
        try:
            if request.model:
                self.prompt_driver.model = request.model
        except Exception as e:
            details = f"Error configuring agent: {e}"
            logger.error(details)
            return ConfigureAgentPromptDriverResultFailure()
        return ConfigureAgentPromptDriverResultSuccess()

    def on_handle_configure_agent_conversation_memory_request(
        self, request: ConfigureAgentConversationMemoryRequest
    ) -> ResultPayload:
        try:
            if request.reset_conversation_memory:
                self.conversation_memory = ConversationMemory()
        except Exception as e:
            details = f"Error configuring agent: {e}"
            logger.error(details)
            return ConfigureAgentConversationMemoryResultFailure()
        return ConfigureAgentConversationMemoryResultSuccess()

    def on_handle_get_conversation_memory_request(self, _: GetConversationMemoryRequest) -> ResultPayload:
        try:
            conversation_memory = self.conversation_memory.runs
        except Exception as e:
            details = f"Error getting conversation memory: {e}"
            logger.error(details)
            return GetConversationMemoryResultFailure()
        return GetConversationMemoryResultSuccess(runs=conversation_memory)
