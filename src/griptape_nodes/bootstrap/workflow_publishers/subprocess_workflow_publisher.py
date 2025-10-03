from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import anyio

from griptape_nodes.bootstrap.utils.python_subprocess_executor import PythonSubprocessExecutor
from griptape_nodes.bootstrap.workflow_publishers.local_workflow_publisher import LocalWorkflowPublisher

if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger(__name__)


class SubprocessWorkflowPublisherError(Exception):
    """Exception raised during subprocess workflow publishing."""


class SubprocessWorkflowPublisher(LocalWorkflowPublisher, PythonSubprocessExecutor):
    def __init__(self) -> None:
        PythonSubprocessExecutor.__init__(self)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return

    async def arun(
        self,
        workflow_name: str,
        workflow_path: str,
        publisher_name: str,
        published_workflow_file_name: str,
        **kwargs: Any,
    ) -> None:
        """Publish a workflow in a subprocess and wait for completion."""
        script_path = Path(__file__).parent / "utils" / "subprocess_script.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_workflow_path = Path(tmpdir) / "workflow.py"
            tmp_script_path = Path(tmpdir) / "subprocess_script.py"

            try:
                async with (
                    await anyio.open_file(workflow_path, "rb") as src,
                    await anyio.open_file(tmp_workflow_path, "wb") as dst,
                ):
                    await dst.write(await src.read())

                async with (
                    await anyio.open_file(script_path, "rb") as src,
                    await anyio.open_file(tmp_script_path, "wb") as dst,
                ):
                    await dst.write(await src.read())
            except Exception as e:
                msg = f"Failed to copy workflow or script to temp directory: {e}"
                logger.exception(msg)
                raise SubprocessWorkflowPublisherError(msg) from e

            args = [
                "--workflow-name",
                workflow_name,
                "--workflow-path",
                str(tmp_workflow_path),
                "--publisher-name",
                publisher_name,
                "--published-workflow-file-name",
                published_workflow_file_name,
            ]
            if kwargs.get("pickle_control_flow_result"):
                args.append("--pickle-control-flow-result")
            await self.execute_python_script(
                script_path=tmp_script_path,
                args=args,
                cwd=Path(tmpdir),
            )
