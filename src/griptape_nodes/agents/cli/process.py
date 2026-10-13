"""Run a CLI that streams JSON Lines on stdout, with cancellation.

Every CLI harness runs its agent as a subprocess that writes one JSON record per
line. :func:`run_jsonl_process` feeds each record to a callback as it arrives,
keeps the end of stderr for error messages, and stops the whole process tree
when the turn is cancelled: a CLI's own children (MCP servers, shell commands)
would otherwise outlive it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence
    from pathlib import Path

logger = logging.getLogger("griptape_nodes")

# A record can carry a whole file or tool result, far past asyncio's 64 KiB default.
_STREAM_LIMIT_BYTES = 64 * 1024 * 1024
_STDERR_TAIL_LINES = 40
_TERMINATE_GRACE_SECONDS = 5.0


@dataclass(frozen=True)
class ProcessExit:
    """``returncode`` is ``None`` when the turn is cancelled."""

    returncode: int | None
    stderr_tail: str
    cancelled: bool


async def run_jsonl_process(  # noqa: PLR0913
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    stdin: bytes | None,
    on_record: Callable[[dict[str, Any]], Awaitable[None]],
    cancel_event: asyncio.Event | None,
) -> ProcessExit:
    """Skip invalid JSON lines and non-object values.

    Callback exceptions stop the process and propagate.
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env=dict(env),
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=_STREAM_LIMIT_BYTES,
        **_process_group_kwargs(),
    )
    stderr_lines: deque[str] = deque(maxlen=_STDERR_TAIL_LINES)
    stderr_task = asyncio.ensure_future(_drain_stderr(process, stderr_lines))
    reader = asyncio.ensure_future(_read_records(process, stdin, on_record))
    try:
        cancelled = await _await_reader(reader, cancel_event)
    except BaseException:
        await _stop(process)
        raise
    finally:
        if not reader.done():
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader

    if cancelled:
        await _stop(process)
        returncode = None
    else:
        returncode = await process.wait()
    with contextlib.suppress(asyncio.CancelledError):
        await stderr_task
    return ProcessExit(returncode=returncode, stderr_tail="\n".join(stderr_lines), cancelled=cancelled)


async def _await_reader(reader: asyncio.Future[None], cancel_event: asyncio.Event | None) -> bool:
    if cancel_event is None:
        await reader
        return False
    cancel_waiter = asyncio.ensure_future(cancel_event.wait())
    try:
        await asyncio.wait({reader, cancel_waiter}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        cancel_waiter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cancel_waiter
    if reader.done():
        reader.result()
        return False
    return True


async def _read_records(
    process: asyncio.subprocess.Process,
    stdin: bytes | None,
    on_record: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    if stdin is not None and process.stdin is not None:
        # A CLI that exits before reading its input closes the pipe; its exit
        # code and stderr then say why, so the write error adds nothing.
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            process.stdin.write(stdin)
            await process.stdin.drain()
        process.stdin.close()
    if process.stdout is None:
        return
    async for raw_line in process.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Skipping a line from the agent CLI that is not JSON: %s", line[:240])
            continue
        if not isinstance(record, dict):
            continue
        await on_record(record)


async def _drain_stderr(process: asyncio.subprocess.Process, lines: deque[str]) -> None:
    if process.stderr is None:
        return
    async for raw_line in process.stderr:
        line = raw_line.decode("utf-8", errors="replace").rstrip()
        if line:
            lines.append(line)


async def _stop(process: asyncio.subprocess.Process) -> None:
    """Stop the process and its children: politely first, then forcefully."""
    if process.returncode is not None:
        return
    _signal_tree(process, force=False)
    try:
        await asyncio.wait_for(process.wait(), timeout=_TERMINATE_GRACE_SECONDS)
    except TimeoutError:
        _signal_tree(process, force=True)
        await process.wait()


def _signal_tree(process: asyncio.subprocess.Process, *, force: bool) -> None:
    if sys.platform == "win32":
        # taskkill /T reaches the children; terminate() alone stops only the CLI.
        args = ["taskkill", "/T", "/PID", str(process.pid)]
        if force:
            args.insert(1, "/F")
        with contextlib.suppress(OSError):
            subprocess.run(args, check=False, capture_output=True)  # noqa: S603
        return
    sig = signal.SIGKILL if force else signal.SIGTERM
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, sig)


def _process_group_kwargs() -> dict[str, Any]:
    """Start the CLI in its own process group so it can be stopped with its children."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}
