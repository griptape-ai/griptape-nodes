"""End-to-end: drive `AgentManager` through real RunAgentRequest events.

This script bypasses the engine's MCP server (we don't bind to localhost in
the spike) but exercises the full request-handling path including:

  * thread creation,
  * Pydantic AI runner construction with the workspace toolset,
  * streaming-token relay to the chat sidebar's event queue,
  * conversation memory persistence + reload via the new ``ModelMessage``
    storage driver,
  * the new `GetConversationMemoryResultSuccess.messages` shape.

Run from the repo root:

    uv run --group test python scripts/spike_agent_manager.py
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from griptape_nodes.retained_mode.events.agent_events import (
    GetConversationMemoryRequest,
    GetConversationMemoryResultSuccess,
    RunAgentRequest,
    RunAgentResultFailure,
    RunAgentResultSuccess,
)
from griptape_nodes.retained_mode.managers.agent_manager import AgentManager

ENV_FILE = Path.home() / ".config/griptape_nodes/.env"


async def main() -> None:
    if not os.environ.get("GT_CLOUD_API_KEY") and ENV_FILE.exists():
        load_dotenv(ENV_FILE)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Quiet down noisy upstream loggers; keep our own at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Build the manager without wiring it into the engine event bus.
    # `static_files_manager` is irrelevant for the chat path so we pass a stub.
    class _StubStatic:
        def save_static_file(self, *_args: object, **_kw: object) -> str:
            return "stub://"

    manager = AgentManager(static_files_manager=_StubStatic())  # type: ignore[arg-type]

    # Force a known good model.
    manager._model_name = "gpt-4o"

    # First turn - new thread, no MCP servers.
    print("=== Turn 1 ===")
    req1 = RunAgentRequest(
        input="Write 'banana-1234' to a file called scratch.txt in the workspace, then say done.",
        url_artifacts=[],
        thread_id="",
        additional_mcp_servers=[],
    )
    res1 = await manager.on_handle_run_agent_request(req1)
    if isinstance(res1, RunAgentResultFailure):
        print("FAIL:", res1.result_details)
        return
    assert isinstance(res1, RunAgentResultSuccess)
    print(res1.output)
    thread_id = res1.thread_id

    # Second turn - same thread, ask it to recall the value.
    print("\n=== Turn 2 ===")
    req2 = RunAgentRequest(
        input="What value did you put in scratch.txt? Read the file and tell me.",
        url_artifacts=[],
        thread_id=thread_id,
        additional_mcp_servers=[],
    )
    res2 = await manager.on_handle_run_agent_request(req2)
    if isinstance(res2, RunAgentResultFailure):
        print("FAIL:", res2.result_details)
        return
    assert isinstance(res2, RunAgentResultSuccess)
    print(res2.output)

    # Inspect persisted memory in the new shape.
    print("\n=== GetConversationMemory ===")
    mem = manager.on_handle_get_conversation_memory_request(GetConversationMemoryRequest(thread_id=thread_id))
    assert isinstance(mem, GetConversationMemoryResultSuccess)
    print(f"messages persisted: {len(mem.messages)}")
    for i, m in enumerate(mem.messages):
        kinds = [p.get("part_kind") for p in m.get("parts", [])]
        print(f"  [{i}] kind={m.get('kind')} parts={kinds}")

    if "1234" in res2.output["text"]:
        print("\n=> recall + persistence works.")
    else:
        print("\n=> WARN: agent did not recall the value.")


if __name__ == "__main__":
    asyncio.run(main())
