"""Auto-load agent skills from ``.agents/skills/*/SKILL.md`` into instructions.

A *skill* is a markdown file at ``<workspace>/.agents/skills/<name>/SKILL.md``.
The file conventionally starts with a YAML front-matter block carrying the
skill's ``name`` and ``description`` (a few sentences describing when an agent
should reach for it), followed by the body, which is a focused prose guide for
operating against a specific tool surface (e.g. the Griptape Nodes MCP server).

This module discovers every ``SKILL.md`` it can find under that directory and
returns a single concatenated string suitable for prepending to the agent's
instructions. Each skill is wrapped in clearly delimited sections so the model
can tell which guidance came from which file.

Files larger than :data:`MAX_SKILL_BYTES` are truncated with a marker; the
overall string is capped at :data:`MAX_TOTAL_BYTES`. These caps exist so a
runaway skill collection cannot dominate the model's context window.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


SKILLS_DIRECTORY = ".agents/skills"
MAX_SKILL_BYTES = 32 * 1024
MAX_TOTAL_BYTES = 96 * 1024


def load_skills(workspace_root: Path) -> str | None:
    """Return concatenated skill text for the workspace, or ``None`` if none found.

    Lookup order is alphabetical by directory name so the result is stable
    across runs.
    """
    skills_root = workspace_root / SKILLS_DIRECTORY
    if not skills_root.is_dir():
        return None

    sections: list[str] = []
    used_bytes = 0
    skill_files = sorted(skills_root.glob("*/SKILL.md"))
    for skill_file in skill_files:
        if not skill_file.is_file():
            continue
        body = _read_truncated(skill_file)
        if not body.strip():
            continue
        skill_name = skill_file.parent.name
        section = f"--- BEGIN skill: {skill_name} ---\n{body.rstrip()}\n--- END skill: {skill_name} ---"
        if used_bytes + len(section) > MAX_TOTAL_BYTES:
            sections.append(
                f"[skill {skill_name!r} omitted: total skill bytes exceed {MAX_TOTAL_BYTES}]",
            )
            break
        sections.append(section)
        used_bytes += len(section)

    if not sections:
        return None

    header = (
        "Available skills (read these before tackling a task they apply to; the "
        "skill's front-matter `description` says when to reach for it):\n\n"
    )
    return header + "\n\n".join(sections)


def _read_truncated(path: Path) -> str:
    with path.open("rb") as fh:
        data = fh.read(MAX_SKILL_BYTES + 1)
    if len(data) > MAX_SKILL_BYTES:
        return data[:MAX_SKILL_BYTES].decode("utf-8", errors="replace") + (
            f"\n\n[truncated at {MAX_SKILL_BYTES} bytes]"
        )
    return data.decode("utf-8", errors="replace")
