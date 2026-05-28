"""Unit tests for the workspace-rooted toolset."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from griptape_nodes.agents.pydantic_ai.workspace_tools import (
    WorkspaceToolset,
    WorkspaceToolsetConfig,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def workspace(tmp_path: Path) -> WorkspaceToolset:
    """Build a workspace toolset rooted at a tmp dir with a couple of seed files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')\n")
    (tmp_path / "README.md").write_text("# project\n")
    return WorkspaceToolset(WorkspaceToolsetConfig(workspace_root=tmp_path))


class TestReadFile:
    def test_reads_existing_file(self, workspace: WorkspaceToolset) -> None:
        assert "hello" in workspace.read_file("src/main.py")

    def test_missing_file_raises(self, workspace: WorkspaceToolset) -> None:
        with pytest.raises(FileNotFoundError):
            workspace.read_file("does_not_exist.txt")

    def test_directory_raises(self, workspace: WorkspaceToolset) -> None:
        with pytest.raises(IsADirectoryError):
            workspace.read_file("src")

    def test_truncates_oversize_files(self, tmp_path: Path) -> None:
        (tmp_path / "big.txt").write_text("x" * 5000)
        ws = WorkspaceToolset(WorkspaceToolsetConfig(workspace_root=tmp_path, max_file_bytes=100))
        body = ws.read_file("big.txt")
        assert body.startswith("x" * 100)
        assert "[truncated at 100 bytes]" in body


class TestWriteFile:
    def test_creates_parents(self, workspace: WorkspaceToolset, tmp_path: Path) -> None:
        result = workspace.write_file("a/b/c/new.txt", "hi")
        assert (tmp_path / "a/b/c/new.txt").read_text() == "hi"
        assert "Wrote" in result

    def test_rejects_oversize_payload(self, workspace: WorkspaceToolset) -> None:
        ws = WorkspaceToolset(
            WorkspaceToolsetConfig(workspace_root=workspace.root, max_file_bytes=10),
        )
        with pytest.raises(ValueError, match="exceeds"):
            ws.write_file("oversize.txt", "x" * 100)

    def test_blocks_path_outside_workspace(self, workspace: WorkspaceToolset, tmp_path: Path) -> None:
        outside = tmp_path.parent / "escape.txt"
        with pytest.raises(PermissionError):
            workspace.write_file(str(outside), "nope")

    def test_blocks_traversal(self, workspace: WorkspaceToolset) -> None:
        with pytest.raises(PermissionError):
            workspace.write_file("../escape.txt", "nope")


class TestEditFile:
    def test_unique_replacement(self, workspace: WorkspaceToolset, tmp_path: Path) -> None:
        workspace.edit_file("src/main.py", "hello", "world")
        assert "world" in (tmp_path / "src/main.py").read_text()

    def test_no_match_raises(self, workspace: WorkspaceToolset) -> None:
        with pytest.raises(ValueError, match="not found"):
            workspace.edit_file("src/main.py", "nope", "yes")

    def test_multiple_matches_raises(self, workspace: WorkspaceToolset, tmp_path: Path) -> None:
        (tmp_path / "src" / "main.py").write_text("a\na\n")
        with pytest.raises(ValueError, match="matched 2 times"):
            workspace.edit_file("src/main.py", "a", "b")


class TestGlob:
    def test_finds_python_files(self, workspace: WorkspaceToolset) -> None:
        results = workspace.glob_files("**/*.py")
        assert results == ["src/main.py"]

    def test_excludes_hidden(self, workspace: WorkspaceToolset, tmp_path: Path) -> None:
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "x.py").write_text("")
        assert ".hidden/x.py" not in workspace.glob_files("**/*.py")


class TestGrep:
    def test_finds_lines(self, workspace: WorkspaceToolset) -> None:
        results = workspace.grep_files(r"def \w+", glob="**/*.py")
        assert any("def main" in r for r in results)

    def test_invalid_regex_raises(self, workspace: WorkspaceToolset) -> None:
        with pytest.raises(ValueError, match="Invalid regex"):
            workspace.grep_files("(unbalanced")


@pytest.mark.asyncio
class TestShell:
    async def test_runs_command(self, workspace: WorkspaceToolset) -> None:
        out = await workspace.shell("echo hello")
        assert "exit_code=0" in out
        assert "hello" in out

    async def test_denylist_blocks(self, tmp_path: Path) -> None:
        ws = WorkspaceToolset(
            WorkspaceToolsetConfig(workspace_root=tmp_path, shell_denylist=("rm",)),
        )
        with pytest.raises(PermissionError, match="denylist"):
            await ws.shell("rm -rf /")

    async def test_allowlist_blocks_unknown(self, tmp_path: Path) -> None:
        ws = WorkspaceToolset(
            WorkspaceToolsetConfig(workspace_root=tmp_path, shell_allowlist=("echo",)),
        )
        with pytest.raises(PermissionError, match="allowlist"):
            await ws.shell("ls")

    async def test_disabled_raises(self, tmp_path: Path) -> None:
        ws = WorkspaceToolset(
            WorkspaceToolsetConfig(workspace_root=tmp_path, shell_enabled=False),
        )
        with pytest.raises(PermissionError, match="disabled"):
            await ws.shell("echo nope")

    async def test_timeout(self, tmp_path: Path) -> None:
        ws = WorkspaceToolset(
            WorkspaceToolsetConfig(workspace_root=tmp_path, shell_timeout_seconds=0.2),
        )
        with pytest.raises(TimeoutError):
            await ws.shell("sleep 5")


class TestConstruction:
    def test_missing_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            WorkspaceToolset(WorkspaceToolsetConfig(workspace_root=tmp_path / "nope"))
