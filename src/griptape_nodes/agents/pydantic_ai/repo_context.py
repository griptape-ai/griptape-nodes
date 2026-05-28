"""Auto-load repository context files (``AGENTS.md`` / ``CLAUDE.md``).

When the workspace contains conventional context files, they are read once at
runner construction time and prepended to the agent's instructions. This
mirrors what Claude Code and other coding agents do: the user keeps a
project-specific guide on disk, and every conversation in that workspace
starts already aware of it.

Lookup order (first match wins per filename, full set is concatenated):

  1. ``AGENTS.md`` at the workspace root
  2. ``CLAUDE.md`` at the workspace root
  3. ``.agents/instructions.md`` if present

Files larger than :data:`MAX_CONTEXT_BYTES` are truncated with a marker so a
runaway file never blows out the conversation budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


CONTEXT_FILE_NAMES = ("AGENTS.md", "CLAUDE.md", ".agents/instructions.md")
MAX_CONTEXT_BYTES = 16 * 1024


def load_repo_context(workspace_root: Path) -> str | None:
    """Return concatenated repo-context text, or ``None`` if nothing was found.

    The result is wrapped in clearly-delimited sections so the model can tell
    which file each chunk came from.
    """
    sections: list[str] = []
    for name in CONTEXT_FILE_NAMES:
        path = workspace_root / name
        if not path.is_file():
            continue
        body = _read_truncated(path)
        if not body.strip():
            continue
        sections.append(f"--- BEGIN {name} ---\n{body.rstrip()}\n--- END {name} ---")

    if not sections:
        return None
    header = "Repository context (read these before doing work; the user expects you to follow these conventions):\n\n"
    return header + "\n\n".join(sections)


def _read_truncated(path: Path) -> str:
    with path.open("rb") as fh:
        data = fh.read(MAX_CONTEXT_BYTES + 1)
    if len(data) > MAX_CONTEXT_BYTES:
        return data[:MAX_CONTEXT_BYTES].decode("utf-8", errors="replace") + (
            f"\n\n[truncated at {MAX_CONTEXT_BYTES} bytes]"
        )
    return data.decode("utf-8", errors="replace")
