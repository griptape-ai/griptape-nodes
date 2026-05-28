"""Tests for the repo-context auto-loader."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.agents.pydantic_ai.repo_context import (
    MAX_CONTEXT_BYTES,
    load_repo_context,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_returns_none_when_no_context_files(tmp_path: Path) -> None:
    """Empty workspace yields no context."""
    assert load_repo_context(tmp_path) is None


def test_picks_up_agents_md(tmp_path: Path) -> None:
    """A top-level AGENTS.md is wrapped in delimiters."""
    (tmp_path / "AGENTS.md").write_text("Use `rg` not `grep`.")
    out = load_repo_context(tmp_path)
    assert out is not None
    assert "BEGIN AGENTS.md" in out
    assert "Use `rg` not `grep`." in out
    assert "END AGENTS.md" in out


def test_concats_multiple_files_in_order(tmp_path: Path) -> None:
    """When multiple context files exist, they're concatenated in lookup order."""
    (tmp_path / "AGENTS.md").write_text("agents-doc")
    (tmp_path / "CLAUDE.md").write_text("claude-doc")
    out = load_repo_context(tmp_path)
    assert out is not None
    agents_pos = out.find("agents-doc")
    claude_pos = out.find("claude-doc")
    assert 0 < agents_pos < claude_pos


def test_truncates_oversize_files(tmp_path: Path) -> None:
    """Files larger than the cap are truncated with a marker."""
    (tmp_path / "AGENTS.md").write_text("x" * (MAX_CONTEXT_BYTES + 1000))
    out = load_repo_context(tmp_path)
    assert out is not None
    assert "[truncated" in out


def test_skips_empty_files(tmp_path: Path) -> None:
    """Whitespace-only context files are ignored."""
    (tmp_path / "AGENTS.md").write_text("   \n  \n")
    assert load_repo_context(tmp_path) is None
