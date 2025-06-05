import logging

from griptape.artifacts import ErrorArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.memory.structure import ConversationMemory
from griptape.tasks import PromptTask

from griptape_nodes.retained_mode.events.agent_events import (
    ConfigureAgentRequest,
    ConfigureAgentResultFailure,
    ConfigureAgentResultSuccess,
    GetConversationMemoryRequest,
    GetConversationMemoryResultFailure,
    GetConversationMemoryResultSuccess,
    ResetAgentConversationMemoryRequest,
    ResetAgentConversationMemoryResultFailure,
    ResetAgentConversationMemoryResultSuccess,
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
        self.prompt_driver = None

        if event_manager is not None:
            event_manager.assign_manager_to_request_type(RunAgentRequest, self.on_handle_run_agent_request)
            event_manager.assign_manager_to_request_type(ConfigureAgentRequest, self.on_handle_configure_agent_request)
            event_manager.assign_manager_to_request_type(
                ResetAgentConversationMemoryRequest, self.on_handle_reset_agent_conversation_memory_request
            )
            event_manager.assign_manager_to_request_type(
                GetConversationMemoryRequest, self.on_handle_get_conversation_memory_request
            )

    def _initialize_prompt_driver(self) -> GriptapeCloudPromptDriver:
        api_key = secrets_manager.get_secret(API_KEY_ENV_VAR)
        if not api_key:
            msg = f"Secret '{API_KEY_ENV_VAR}' not found"
            raise ValueError(msg)
        return GriptapeCloudPromptDriver(api_key=api_key)

    def on_handle_run_agent_request(self, request: RunAgentRequest) -> ResultPayload:
        try:
            if self.prompt_driver is None:
                self.prompt_driver = self._initialize_prompt_driver()
            task_output = PromptTask(
                request.input, prompt_driver=self.prompt_driver, conversation_memory=self.conversation_memory
            ).run()
            if isinstance(task_output, ErrorArtifact):
                details = f"Error running agent: {task_output.value}"
                logger.error(details)
                return RunAgentResultFailure(error=task_output.to_json())
            return RunAgentResultSuccess(output=task_output.to_json())
        except Exception as e:
            return RunAgentResultFailure(ErrorArtifact(e).to_json())

    def on_handle_configure_agent_request(self, request: ConfigureAgentRequest) -> ResultPayload:
        try:
            if self.prompt_driver is None:
                self.prompt_driver = self._initialize_prompt_driver()
            for key, value in request.prompt_driver.items():
                setattr(self.prompt_driver, key, value)
        except Exception as e:
            details = f"Error configuring agent: {e}"
            logger.error(details)
            return ConfigureAgentResultFailure()
        return ConfigureAgentResultSuccess()

    def on_handle_reset_agent_conversation_memory_request(
        self, _: ResetAgentConversationMemoryRequest
    ) -> ResultPayload:
        try:
            self.conversation_memory = ConversationMemory()
        except Exception as e:
            details = f"Error resetting agent conversation memory: {e}"
            logger.error(details)
            return ResetAgentConversationMemoryResultFailure()
        return ResetAgentConversationMemoryResultSuccess()

    def on_handle_get_conversation_memory_request(self, _: GetConversationMemoryRequest) -> ResultPayload:
        try:
            conversation_memory = self.conversation_memory.runs
        except Exception as e:
            details = f"Error getting conversation memory: {e}"
            logger.error(details)
            return GetConversationMemoryResultFailure()
        return GetConversationMemoryResultSuccess(runs=conversation_memory)
