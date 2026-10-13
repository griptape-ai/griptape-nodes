"""Keep stdio MCP environment secrets off Codex's command line.

This script runs independently of the engine and must not import it.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    """Run the server command with the file's variables added to the environment."""
    env_file, command, *args = argv
    env = {**os.environ, **json.loads(Path(env_file).read_text(encoding="utf-8"))}
    # Finds commands such as `npx.cmd` on Windows, which subprocess won't.
    command = shutil.which(command, path=env.get("PATH")) or command
    if sys.platform == "win32":
        # os.exec* on Windows exits this process early, which the CLI reads as the server stopping.
        return subprocess.run([command, *args], env=env, check=False).returncode  # noqa: S603
    os.execvpe(command, [command, *args], env)  # noqa: S606
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
