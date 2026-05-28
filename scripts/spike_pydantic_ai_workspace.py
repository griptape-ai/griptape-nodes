"""Drive the Pydantic AI agent through a real coding task using the workspace toolset.

The agent runs against Griptape Cloud with `gpt-4o`, given a fresh tmp dir as
its workspace, and is asked to do a small multi-step file task:

  1. Create a Python file that prints "hello, pydantic"
  2. Add a second function
  3. Use grep to confirm the function exists
  4. Run the file via the shell tool

Run from the repo root:

    uv run --group test python scripts/spike_pydantic_ai_workspace.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent

from griptape_nodes.agents.pydantic_ai import (
    GriptapeCloudModel,
    WorkspaceToolsetConfig,
    register_workspace_tools,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ENV_FILE = Path.home() / ".config/griptape_nodes/.env"


async def main() -> None:
    if not os.environ.get("GT_CLOUD_API_KEY") and ENV_FILE.exists():
        load_dotenv(ENV_FILE)

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        agent = Agent(
            GriptapeCloudModel("gpt-4o"),
            instructions=(
                "You are a coding assistant operating inside a workspace. "
                "Use the tools you have to create, edit, search and run code. "
                "When the task is done, respond with a one-line summary."
            ),
        )
        register_workspace_tools(
            agent,
            WorkspaceToolsetConfig(
                workspace_root=tmp,
                shell_allowlist=("echo", "python3", "python", "ls", "cat", "wc"),
            ),
        )

        prompt = (
            "1. Write a Python file `hello.py` that defines a function `greet(name)` "
            "which returns 'hello, ' followed by the name, and a `__main__` block that "
            "prints greet('pydantic').\n"
            "2. Edit it to add a second function `shout(text)` that returns text upper-cased.\n"
            "3. Use grep_files to confirm both functions are present.\n"
            "4. Run `python3 hello.py` via the shell tool and report the output.\n"
            "When all four steps are done, respond with a single sentence summarizing the result."
        )
        result = await agent.run(prompt)
        for p in sorted(tmp.rglob("*")):
            if p.is_file():
                pass
        for msg in result.all_messages():
            for part in msg.parts:
                if part.__class__.__name__ == "ToolCallPart":
                    pass


if __name__ == "__main__":
    asyncio.run(main())
