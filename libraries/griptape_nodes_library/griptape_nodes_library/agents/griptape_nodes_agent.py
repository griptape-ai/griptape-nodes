from griptape.artifacts import TextArtifact
from griptape.memory.structure import Run
from griptape.structures import Agent
from griptape.tasks import BaseTask


class GriptapeNodesAgent(Agent):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.orig_tasks = None
        self._context = None

    def build_context(self, prompt=str | None) -> str:  # noqa: ANN001
        conversation_memory = []
        context = ""
        if len(self.conversation_memory.runs) > 0:  # type: ignore  # noqa: PGH003
            # Build the context from the conversation memory
            for run in self.conversation_memory.runs:  # type: ignore  # noqa: PGH003
                if run.input:
                    conversation_memory.append(f"User: {run.input.value}")
                if run.output:
                    conversation_memory.append(f"Assistant: {run.output.value}")
            context = "\n".join(conversation_memory)
            context = f"<Conversation History>\n{context}</Conversation History>\n"
        if prompt:
            # Add the prompt to the context
            context = f"{context}\nUser:\n{prompt}\n"
        self._context = context
        return context

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
