from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class PythonSubprocessExecutorError(Exception):
    """Exception raised during Python subprocess execution."""


class PythonSubprocessExecutor:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._is_running = False

    async def execute_python_script(
        self, script_path: Path, args: list[str] | None = None, cwd: Path | None = None
    ) -> None:
        """Execute a Python script in a subprocess and wait for completion.

        Args:
            script_path: Path to the Python script to execute
            args: Additional command line arguments
            cwd: Working directory for the subprocess
        """
        if self.is_running():
            logger.warning("Another subprocess is already running. Terminating it first.")
            await self.terminate()

        args = args or []
        command = [sys.executable, str(script_path), *args]

        try:
            logger.info("Starting subprocess: %s", " ".join(command))
            logger.info("Working directory: %s", cwd)

            self._process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._is_running = True
            logger.info("Subprocess started with PID: %s", self._process.pid)

            stdout_bytes, stderr_bytes = await self._process.communicate()
            returncode = self._process.returncode
            stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""

            # Log all output regardless of return code
            if stdout:
                logger.info("Subprocess stdout: %s", stdout)
            if stderr:
                logger.info("Subprocess stderr: %s", stderr)

            if returncode == 0:
                logger.info("Subprocess completed successfully with return code: %d", returncode)
            else:
                logger.error("Subprocess failed with return code: %d", returncode)
                msg = f"Subprocess failed with return code: {returncode}"
                raise RuntimeError(msg)  # noqa: TRY301

        except Exception as e:
            msg = f"Error running subprocess: {e}"
            logger.exception(msg)
            raise PythonSubprocessExecutorError(msg) from e
        finally:
            self._is_running = False
            self._process = None

    def is_running(self) -> bool:
        """Check if a subprocess is currently running."""
        return self._is_running

    async def terminate(self) -> bool:
        """Terminate the running subprocess.

        Returns:
            True if successfully terminated, False otherwise
        """
        if not self.is_running() or not self._process:
            return True

        try:
            logger.info("Terminating subprocess...")
            self._process.terminate()

            # Wait for graceful termination with timeout using context manager
            try:
                async with asyncio.timeout(5.0):
                    await self._process.wait()
                logger.info("Subprocess terminated gracefully")
                return True  # noqa: TRY300
            except TimeoutError:
                logger.warning("Subprocess did not terminate gracefully, force killing...")
                self._process.kill()
                await self._process.wait()
                logger.info("Subprocess force killed")
                return True

        except Exception as e:
            logger.error("Error terminating subprocess: %s", e)
            return False
        finally:
            self._is_running = False
            self._process = None

    def get_status(self) -> dict[str, Any]:
        """Get current status information."""
        return {
            "is_running": self.is_running(),
            "has_process": self._process is not None,
            "process_pid": self._process.pid if self._process else None,
        }
