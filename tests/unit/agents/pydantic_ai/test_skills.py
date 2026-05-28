"""Tests for the skills auto-loader."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.agents.pydantic_ai.skills import (
    MAX_SKILL_BYTES,
    load_skills,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_returns_none_when_directory_missing(tmp_path: Path) -> None:
    """Workspace with no `.agents/skills` dir yields no skill content."""
    assert load_skills(tmp_path) is None


def test_returns_none_when_no_skills(tmp_path: Path) -> None:
    """Empty skills directory yields no content."""
    (tmp_path / ".agents/skills").mkdir(parents=True)
    assert load_skills(tmp_path) is None


def test_loads_single_skill(tmp_path: Path) -> None:
    """One skill produces a header + a single delimited section."""
    skill_dir = tmp_path / ".agents/skills/my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("body content here")
    out = load_skills(tmp_path)
    assert out is not None
    assert "BEGIN skill: my-skill" in out
    assert "body content here" in out
    assert "END skill: my-skill" in out


def test_loads_multiple_skills_alphabetically(tmp_path: Path) -> None:
    """Multiple skills are emitted in alphabetical directory order."""
    base = tmp_path / ".agents/skills"
    (base / "zeta").mkdir(parents=True)
    (base / "zeta/SKILL.md").write_text("zeta-body")
    (base / "alpha").mkdir(parents=True)
    (base / "alpha/SKILL.md").write_text("alpha-body")

    out = load_skills(tmp_path)
    assert out is not None
    assert out.find("alpha-body") < out.find("zeta-body")


def test_truncates_oversize_skill(tmp_path: Path) -> None:
    """Files larger than MAX_SKILL_BYTES are truncated with a marker."""
    skill_dir = tmp_path / ".agents/skills/big"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("x" * (MAX_SKILL_BYTES + 100))
    out = load_skills(tmp_path)
    assert out is not None
    assert "[truncated" in out


def test_overall_byte_cap_drops_later_skills(tmp_path: Path) -> None:
    """Once the running total would exceed MAX_TOTAL_BYTES, later skills are skipped."""
    base = tmp_path / ".agents/skills"
    # Five skills near the per-skill cap. Total well exceeds MAX_TOTAL_BYTES so
    # the loader has to drop something.
    for name in ("a", "b", "c", "d", "e"):
        (base / name).mkdir(parents=True)
        (base / name / "SKILL.md").write_text("y" * (MAX_SKILL_BYTES - 200))

    out = load_skills(tmp_path)
    assert out is not None
    assert "BEGIN skill: a" in out
    assert "omitted: total skill bytes exceed" in out


def test_skips_empty_skill_files(tmp_path: Path) -> None:
    """Whitespace-only SKILL.md files are ignored."""
    skill_dir = tmp_path / ".agents/skills/empty"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("   \n   \n")
    assert load_skills(tmp_path) is None
