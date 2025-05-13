from griptape.artifacts import TextArtifact
from griptape.memory.structure import Run
from griptape.structures import Agent
from griptape.tasks import BaseTask
from griptape.tools import BaseTool


class GriptapeNodesAgent(Agent):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.orig_tasks = None
        self._context = {}

    def build_context(self) -> str | dict:
        conversation_memory = []
        # Build the context from the conversation memory
        for run in self.conversation_memory.runs:  # type: ignore  # noqa: PGH003
            if run.input:
                conversation_memory.append(f"User: {run.input.value}")
            if run.output:
                conversation_memory.append(f"Assistant: {run.output.value}")
        self._context = {"conversation_memory": conversation_memory}
        return self._context

    def swap_tool(self, tool: BaseTool) -> None:
        # swap the tool with a new one
        self._orig_tools = self.tools
        # Replace the task with the new one
        self.tools = [tool]

    def restore_tool(self) -> None:
        # restore the original tool
        if self._orig_tools:
            self.tools = self._orig_tools

    def swap_task(self, task: BaseTask) -> None:
        # swap the task with a new one
        self._orig_tasks = self._tasks[0]

        # Replace the task with the new one
        self.add_tasks(task)

    def restore_task(self) -> None:
        # restore the original task
        if self._orig_tasks:
            self.add_tasks(self._orig_tasks)  # type: ignore  # noqa: PGH003
            self._tasks[0].prompt_driver.stream = True  # type: ignore  # noqa: PGH003

    def insert_false_memory(self, prompt: str, output: str, tool: str | None = None) -> None:
        if tool:
            output += f'\n<THOUGHT>\nmeta={{"used_tool": True, "tool": "{tool}"}}\n</THOUGHT>'

        self.conversation_memory.runs[-1] = Run(  # type: ignore  # noqa: PGH003
            input=TextArtifact(value=prompt),
            output=TextArtifact(value=output),
        )
        self._rulesets[0].rules
