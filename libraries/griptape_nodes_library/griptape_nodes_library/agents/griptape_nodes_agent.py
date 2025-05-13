from griptape.artifacts import TextArtifact
from griptape.memory.structure import Run
from griptape.structures import Agent
from griptape.tasks import BaseTask


class GriptapeNodesAgent(Agent):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.orig_tasks = None

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
