"""Query Knowledge Base node for Griptape Cloud.

Queries a Griptape Cloud Knowledge Base using a RAG pipeline (GriptapeCloudVectorStoreDriver
+ LocalRerankDriver) and returns results via an agent, mirroring the MCP task pattern.
"""

import time
from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.drivers.rerank.local import LocalRerankDriver
from griptape.drivers.vector.griptape_cloud import GriptapeCloudVectorStoreDriver
from griptape.engines.rag import RagEngine
from griptape.engines.rag.modules import (
    PromptResponseRagModule,
    TextChunksRerankRagModule,
    VectorStoreRetrievalRagModule,
)
from griptape.engines.rag.stages import ResponseRagStage, RetrievalRagStage
from griptape.events import ActionChunkEvent, FinishStructureRunEvent, StartStructureRunEvent, TextChunkEvent
from griptape.structures import Agent
from griptape.tasks import PromptTask
from griptape.tools import RagTool

from griptape_cloud.base.base_griptape_cloud_node import BaseGriptapeCloudNode
from griptape_nodes.exe_types.core_types import BadgeData, Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.options import Options


def _knowledge_base_choices_and_data(knowledge_bases: list) -> tuple[list[str], list[dict[str, str]]]:
    """Build choice names and data list for dropdown (Agent model pattern: names in dropdown, id in data)."""
    choices = [kb.name for kb in knowledge_bases]
    data = [{"name": kb.name, "knowledge_base_id": kb.knowledge_base_id} for kb in knowledge_bases]
    return choices, data


BADGE_MESSAGE = """
Select a Knowledge Base to use. 
Use the refresh button to reload the list of Knowledge Bases.

To manage your knowledge bases, visit the [Griptape Cloud Knowledge Base](https://cloud.griptape.ai/knowledge-bases) page.
"""


class QueryKnowledgeBase(SuccessFailureNode, BaseGriptapeCloudNode):
    """Query a Griptape Cloud Knowledge Base using a RAG pipeline and optional agent."""

    def __init__(self, name: str | None = None, **kwargs) -> None:
        if name is not None:
            kwargs["name"] = name
        super().__init__(**kwargs)

        # Get available knowledge bases for the dropdown (Agent pattern: names in dropdown, id in ui_options data)
        knowledge_bases = []
        try:
            response = self._list_knowledge_bases()
            knowledge_bases = response.knowledge_bases
        except Exception as e:
            logger.debug("%s: Could not load knowledge bases at init: %s", self.name, e)
        choices, self._kb_choices_data = _knowledge_base_choices_and_data(knowledge_bases)
        default_kb = choices[0] if choices else None

        self.add_parameter(
            Parameter(
                name="knowledge_base_id",
                input_types=["str"],
                type="str",
                default_value=default_kb,
                tooltip="Select a Knowledge Base to use",
                badge=BadgeData(
                    variant="link",
                    title="Griptape Cloud Knowledge Base",
                    message=BADGE_MESSAGE,
                ),
                traits={
                    Options(choices=choices),
                    Button(
                        full_width=False,
                        icon="refresh-cw",
                        size="icon",
                        variant="secondary",
                        on_click=self._reload_knowledge_bases,
                    ),
                },
                ui_options={"display_name": "Knowledge Base", "data": self._kb_choices_data},
            )
        )
        self.add_parameter(
            Parameter(
                name="agent",
                input_types=["Agent"],
                type="Agent",
                output_type="Agent",
                default_value=None,
                tooltip="Optional agent to use - helpful if you want to continue interaction with an existing agent.",
            )
        )
        self.add_parameter(
            ParameterInt(
                name="max_subtasks",
                default_value=20,
                hide=True,
                tooltip="The maximum number of subtasks to allow.",
                min_val=1,
                max_val=100,
            )
        )
        self.add_parameter(
            ParameterString(
                name="prompt",
                default_value=None,
                tooltip="The query to run against the Knowledge Base.",
                multiline=True,
                placeholder_text="Input your question...",
            )
        )
        self.add_parameter(
            ParameterList(
                name="context",
                tooltip="Additional context to add to the prompt",
                input_types=["Any"],
                allowed_modes={ParameterMode.INPUT},
            )
        )
        self.output = ParameterString(
            name="output",
            default_value=None,
            tooltip="The output of the query",
            allowed_modes={ParameterMode.OUTPUT},
            multiline=True,
            markdown=True,
            placeholder_text="The results of the Knowledge Base query will be displayed here.",
        )
        self.add_parameter(self.output)

        self._create_status_parameters(
            result_details_tooltip="Details about the Knowledge Base query execution result",
            result_details_placeholder="Details on the Knowledge Base query execution will be presented here.",
            parameter_group_initially_collapsed=True,
        )

    def _reload_knowledge_bases(self, button: Button, button_details: ButtonDetailsMessagePayload) -> None:  # noqa: ARG002
        """Reload knowledge bases when the refresh button is clicked (same pattern as MCP task)."""
        try:
            response = self._list_knowledge_bases()
            knowledge_bases = response.knowledge_bases
            choices, self._kb_choices_data = _knowledge_base_choices_and_data(knowledge_bases)

            if choices:
                current_value = self.get_parameter_value("knowledge_base_id")
                if current_value in choices:
                    default_value = current_value
                else:
                    default_value = choices[0]
                self._update_option_choices("knowledge_base_id", choices, default_value)
                param = self.get_parameter_by_name("knowledge_base_id")
                if param is not None and hasattr(param, "_ui_options") and param._ui_options is not None:
                    param._ui_options["data"] = self._kb_choices_data
                msg = f"{self.name}: Refreshed knowledge bases: {len(choices)} available"
                logger.info(msg)
            else:
                self._update_option_choices(
                    "knowledge_base_id",
                    ["No knowledge bases available"],
                    "No knowledge bases available",
                )
                self._kb_choices_data = []
                param = self.get_parameter_by_name("knowledge_base_id")
                if param is not None and hasattr(param, "_ui_options") and param._ui_options is not None:
                    param._ui_options["data"] = []
                msg = f"{self.name}: No knowledge bases available"
                logger.info(msg)
        except Exception as e:
            msg = f"{self.name}: Failed to reload knowledge bases: {e}"
            logger.error(msg)

    def _get_resolved_knowledge_base_id(self) -> str | None:
        """Return the knowledge_base_id for API use (resolve selected name from ui_options data)."""
        val = self.get_parameter_value("knowledge_base_id")
        if not val or val == "No knowledge bases available":
            return None
        data = getattr(self, "_kb_choices_data", [])
        entry = next((d for d in data if d.get("name") == val), None)
        if entry is not None:
            return entry.get("knowledge_base_id")
        return val

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate node parameters before execution."""
        exceptions = []

        api_key = None
        try:
            api_key = self._get_gt_cloud_api_key()
        except KeyError as e:
            exceptions.append(e)

        knowledge_base_id = self._get_resolved_knowledge_base_id()
        if not knowledge_base_id:
            msg = (
                f"{self.name}: No Knowledge Base selected. Select one from the list or ensure "  # noqa: S608
                "GT_CLOUD_API_KEY is set and refresh."
            )
            exceptions.append(ValueError(msg))

        prompt = self.get_parameter_value("prompt")
        if not prompt:
            msg = f"{self.name}: No prompt provided. Please enter a query to run against the Knowledge Base."
            exceptions.append(ValueError(msg))

        if api_key is None and exceptions:
            return exceptions

        return exceptions or None

    def _build_rag_tool(self, knowledge_base_id: str) -> RagTool:
        """Build RAG tool with GriptapeCloudVectorStoreDriver and LocalRerankDriver."""
        api_key = self._get_gt_cloud_api_key()
        vector_store_driver = GriptapeCloudVectorStoreDriver(
            api_key=api_key,
            knowledge_base_id=knowledge_base_id,
        )
        rerank_driver = LocalRerankDriver()
        retrieval_stage = RetrievalRagStage(
            retrieval_modules=[
                VectorStoreRetrievalRagModule(
                    name="KBRetriever",
                    vector_store_driver=vector_store_driver,
                ),
            ],
            rerank_module=TextChunksRerankRagModule(rerank_driver=rerank_driver),
        )
        response_stage = ResponseRagStage(
            response_modules=[
                PromptResponseRagModule(
                    prompt_driver=GriptapeCloudPromptDriver(
                        model="gpt-4.1",
                        api_key=api_key,
                        stream=True,
                    ),
                ),
            ],
        )
        rag_engine = RagEngine(
            retrieval_stage=retrieval_stage,
            response_stage=response_stage,
        )
        return RagTool(
            description="Query the Griptape Cloud Knowledge Base for relevant information.",
            off_prompt=False,
            rag_engine=rag_engine,
        )

    def _setup_agent(self) -> tuple[Agent | None, Any, list, list]:
        """Setup agent, driver, tools, and rulesets (mirror MCP task)."""
        rulesets = []
        tools = []
        agent_value = self.get_parameter_value("agent")
        if isinstance(agent_value, dict):
            agent = Agent().from_dict(agent_value)
            task = agent.tasks[0]
            driver = task.prompt_driver
            tools = list(task.tools)
            rulesets = list(task.rulesets)
        else:
            driver = GriptapeCloudPromptDriver(
                model="gpt-4.1",
                api_key=self._get_gt_cloud_api_key(),
                stream=True,
            )
            agent = Agent()
        return agent, driver, tools, rulesets

    def _add_task_to_agent(  # noqa: PLR0913
        self,
        agent: Agent,
        rag_tool: RagTool,
        driver: Any,
        tools: list,
        rulesets: list,
        max_subtasks: int,
    ) -> bool:
        """Add PromptTask with RAG tool to agent."""
        try:
            prompt_task = PromptTask(
                tools=[*tools, rag_tool],
                prompt_driver=driver,
                rulesets=rulesets,
                max_subtasks=max_subtasks,
            )
            agent.add_task(prompt_task)
        except Exception as e:
            msg = f"{self.name}: Failed to add task to agent: {e}"
            logger.error(msg)
            self._handle_failure_exception(e)
            return False
        return True

    def _execute_with_streaming(self, agent: Agent, prompt: str, knowledge_base_id: str) -> None:
        """Execute agent with streaming."""
        try:
            execution_start = time.time()
            logger.debug(
                "%s: Starting agent execution with Knowledge Base '%s'...",
                self.name,
                knowledge_base_id,
            )
            result = self._process_with_streaming(agent, prompt)
            execution_time = time.time() - execution_start
            logger.debug("%s: Agent execution completed in %.2fs", self.name, execution_time)

            self._set_success_output_values(result)
            success_details = f"Successfully executed Knowledge Base query for '{knowledge_base_id}'"
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
            logger.info("%s: %s", self.name, success_details)

        except Exception as execution_error:
            error_details = f"Knowledge Base query failed: {execution_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error("%s: %s", self.name, error_details)
            self._handle_failure_exception(execution_error)

    def _process_with_streaming(self, agent: Agent, prompt: BaseArtifact | str) -> Agent:
        """Process the agent with streaming (mirror MCP task)."""
        args = [prompt] if prompt else []
        structure_id_stack = []
        active_structure_id = None

        task = agent.tasks[0]
        if not isinstance(task, PromptTask):
            msg = "Agent must have a PromptTask"
            raise TypeError(msg)
        prompt_driver = task.prompt_driver

        if prompt_driver.stream:
            for event in agent.run_stream(
                *args,
                event_types=[StartStructureRunEvent, TextChunkEvent, ActionChunkEvent, FinishStructureRunEvent],
            ):
                if isinstance(event, StartStructureRunEvent):
                    active_structure_id = event.structure_id
                    structure_id_stack.append(active_structure_id)
                if isinstance(event, FinishStructureRunEvent):
                    structure_id_stack.pop()
                    active_structure_id = structure_id_stack[-1] if structure_id_stack else None

                if agent.id == active_structure_id:
                    if isinstance(event, TextChunkEvent):
                        self.append_value_to_parameter("output", value=event.token)
                    if isinstance(event, ActionChunkEvent) and event.name:
                        self.append_value_to_parameter("output", f"\n[Using tool {event.name}]\n")
        else:
            agent.run(*args)
            self.append_value_to_parameter("output", value=str(agent.output))

        return agent

    def _set_success_output_values(self, result: Agent) -> None:
        """Set output parameter values on success (remove RagTool from agent like MCP task)."""
        self.parameter_output_values["output"] = str(result.output) if result.output else ""
        if isinstance(result.tasks[0], PromptTask) and result.tasks[0].tools:
            result.tasks[0].tools = [tool for tool in result.tasks[0].tools if not isinstance(tool, RagTool)]
        self.parameter_output_values["agent"] = result.to_dict()

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["output"] = ""

    def process(self) -> AsyncResult:
        """Run Knowledge Base query with RAG tool and agent."""
        self._clear_execution_status()
        self._set_failure_output_values()
        self.publish_update_to_parameter("output", "")

        knowledge_base_id = self._get_resolved_knowledge_base_id()
        prompt = self.get_parameter_value("prompt")
        max_subtasks = self.get_parameter_value("max_subtasks")
        context = self.get_parameter_list_value("context")

        if not knowledge_base_id:
            error_details = "Knowledge Base ID is not set"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error("%s: %s", self.name, error_details)
            return

        if not prompt:
            error_details = "Prompt is not set"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error("%s: %s", self.name, error_details)
            return

        if context:
            prompt = f"{prompt}\n{context!s}"

        agent, driver, tools, rulesets = self._setup_agent()
        if agent is None:
            error_details = "Failed to setup agent"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error("%s: %s", self.name, error_details)
            return

        rag_tool = self._build_rag_tool(knowledge_base_id)
        if not self._add_task_to_agent(agent, rag_tool, driver, tools, rulesets, max_subtasks):
            error_details = "Failed to add task to agent"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error("%s: %s", self.name, error_details)
            return

        yield lambda: self._execute_with_streaming(agent, prompt, knowledge_base_id)
