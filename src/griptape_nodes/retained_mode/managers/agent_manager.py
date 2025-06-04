import logging

from griptape.structures import Agent
from griptape.drivers import GriptapeCloudPromptDriver
from griptape.memory.structure import ConversationMemory

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.agent_events import (
    RunAgentRequest,
    RunAgentResultFailure,
    RunAgentResultSuccess,
    ConfigureAgentRequest,
    ConfigureAgentResultSuccess,
    ConfigureAgentResultFailure,
    GetConversationMemoryRequest,
    GetConversationMemoryResultSuccess,
    GetConversationMemoryResultFailure,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

logger = logging.getLogger("griptape_nodes")

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"

config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)


class AgentManager:
    def __init__(self, event_manager: EventManager | None = None) -> None:
        self.agent = Agent(
            prompt_driver=GriptapeCloudPromptDriver(api_key=secrets_manager.get_secret("GT_CLOUD_API_KEY"))
        )
        self._configure_agent()

        if event_manager is not None:
            event_manager.assign_manager_to_request_type(RunAgentRequest, self.on_handle_run_agent_request)
            event_manager.assign_manager_to_request_type(ConfigureAgentRequest, self.on_handle_reset_agent_request)
            event_manager.assign_manager_to_request_type(
                GetConversationMemoryRequest, self.on_handle_get_conversation_memory_request
            )

    def _configure_agent(self, request: ConfigureAgentRequest = ConfigureAgentRequest()) -> None:
        if request.model:
            self.agent.prompt_driver.model = request.model

        if request.reset_conversation_memory:
            self.agent.conversation_memory = ConversationMemory()

    def on_handle_run_agent_request(self, request: RunAgentRequest) -> ResultPayload:
        try:
            self.agent.run(request.input)
        except Exception as e:
            details = f"Error running agent: {e}"
            logger.error(details)
            return RunAgentResultFailure()
        finally:
            return RunAgentResultSuccess()

    def on_handle_reset_agent_request(self, request: ConfigureAgentRequest) -> ResultPayload:
        try:
            self._configure_agent(request)
        except Exception as e:
            details = f"Error configuring agent: {e}"
            logger.error(details)
            return ConfigureAgentResultFailure()
        finally:
            return ConfigureAgentResultSuccess()

    def on_handle_get_conversation_memory_request(self, request: GetConversationMemoryRequest) -> ResultPayload:
        try:
            conversation_memory = self.agent.conversation_memory.runs
        except Exception as e:
            details = f"Error getting conversation memory: {e}"
            logger.error(details)
            return GetConversationMemoryResultFailure()
        finally:
            return GetConversationMemoryResultSuccess(runs=conversation_memory)
