"""Smoke test the GriptapeCloudModel adapter against the real Griptape Cloud endpoint.

Run with `uv run --group test python scripts/spike_pydantic_ai_agent.py` from the
repo root. Loads `GT_CLOUD_API_KEY` from `~/.config/griptape_nodes/.env`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent

from griptape_nodes.agents.pydantic_ai import GriptapeCloudModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("spike")

ENV_FILE = Path.home() / ".config/griptape_nodes/.env"


async def main() -> None:
    if not os.environ.get("GT_CLOUD_API_KEY") and ENV_FILE.exists():
        load_dotenv(ENV_FILE)

    model = GriptapeCloudModel("gpt-4o")

    agent = Agent(model)
    result = await agent.run("Say the word 'pong' and nothing else.")

    agent_with_tool = Agent(model)

    @agent_with_tool.tool_plain
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    result = await agent_with_tool.run("Use the `add` tool to add 17 and 25, then say only the result.")
    for _m in result.all_messages():
        pass

    async with agent.run_stream("Count from 1 to 5, one number per line.") as stream:
        async for _chunk in stream.stream_text(delta=True):
            pass


if __name__ == "__main__":
    asyncio.run(main())
