"""Workspace-rooted file system and shell tools for the chat-sidebar agent.

Each tool resolves the agent's input path against a fixed workspace root and
refuses anything that escapes that root. The set is intentionally narrow:
just enough surface to do real coding-agent work (read, write, edit, glob,
grep, shell) without giving the model the keys to the rest of the host.

The tools are registered against a `pydantic_ai.Agent` via the helper
:func:`register_workspace_tools`. They take advantage of Pydantic AI's
function-tool support (docstrings become descriptions; signatures become the
JSON schema) so the cloud sees one activity per tool with no extra wiring.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.files.path_utils import canonicalize_for_identity

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic_ai import Agent


DEFAULT_SHELL_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_FILE_BYTES = 256 * 1024  # 256 KiB; agents almost never need more
DEFAULT_MAX_GREP_MATCHES = 200
DEFAULT_MAX_GLOB_MATCHES = 500
DEFAULT_MAX_SHELL_OUTPUT_BYTES = 32 * 1024


@dataclass(frozen=True)
class WorkspaceToolsetConfig:
    """Configuration for the workspace toolset.

    Attributes:
        workspace_root: Absolute path the agent is allowed to read / write under.
            All file paths the agent passes are resolved relative to this root,
            and any resolved path that lands outside of it is rejected.
        shell_enabled: When False, :func:`shell` raises immediately. Useful for
            environments where shell access is unsafe regardless of allowlist.
        shell_allowlist: When non-empty, the shell tool only allows commands
            whose first whitespace-delimited token matches an entry. This is a
            coarse guard, not a sandbox: it cannot see through pipes, ``&&``,
            subshells, or absolute paths.
        shell_denylist: Commands whose first whitespace-delimited token matches
            any entry are rejected (applied after the allowlist). Best-effort
            only and trivially bypassable via shell metacharacters or alternate
            spellings; do not rely on it as a security boundary.
        shell_timeout_seconds: Hard wall-clock cap on each shell invocation.
        max_file_bytes: Cap on bytes returned by ``read_file`` / accepted by
            ``write_file``.
        max_shell_output_bytes: Cap on combined stdout + stderr bytes returned
            by ``shell``.
    """

    workspace_root: Path
    shell_enabled: bool = True
    shell_allowlist: tuple[str, ...] = ()
    shell_denylist: tuple[str, ...] = (
        "rm",
        "sudo",
        "shutdown",
        "reboot",
        "mkfs",
        "dd",
    )
    shell_timeout_seconds: float = DEFAULT_SHELL_TIMEOUT_SECONDS
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_shell_output_bytes: int = DEFAULT_MAX_SHELL_OUTPUT_BYTES


class WorkspaceToolset:
    """Owns the workspace root and exposes the agent-facing tool methods."""

    def __init__(self, config: WorkspaceToolsetConfig) -> None:
        root = canonicalize_for_identity(config.workspace_root)
        if not root.exists() or not root.is_dir():
            msg = f"Workspace root {root} does not exist or is not a directory."
            raise ValueError(msg)
        self._config = config
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def register_on(self, agent: Agent) -> None:
        """Register every workspace tool on the given Pydantic AI agent."""
        agent.tool_plain(self.read_file)
        agent.tool_plain(self.write_file)
        agent.tool_plain(self.edit_file)
        agent.tool_plain(self.glob_files)
        agent.tool_plain(self.grep_files)
        if self._config.shell_enabled:
            agent.tool_plain(self.shell)

    def read_file(self, path: str) -> str:
        """Read a UTF-8 text file inside the workspace and return its contents.

        Args:
            path: Path relative to the workspace root (or absolute inside it).

        Returns:
            The file contents as a string. Files larger than the workspace's
            byte cap are truncated and a marker is appended so the model can
            tell what happened.
        """
        target = self._resolve(path)
        if not target.exists():
            msg = f"File not found: {path}"
            raise FileNotFoundError(msg)
        if not target.is_file():
            msg = f"Path is not a regular file: {path}"
            raise IsADirectoryError(msg)
        max_bytes = self._config.max_file_bytes
        with target.open("rb") as fh:
            data = fh.read(max_bytes + 1)
        truncated = len(data) > max_bytes
        body = data[:max_bytes].decode("utf-8", errors="replace")
        if truncated:
            body += f"\n\n[truncated at {max_bytes} bytes]"
        return body

    def write_file(self, path: str, content: str) -> str:
        """Write a UTF-8 text file inside the workspace, creating parents as needed.

        Args:
            path: Path relative to the workspace root (or absolute inside it).
            content: Text to write. The file is overwritten.

        Returns:
            A short confirmation message including the resolved relative path.
        """
        target = self._resolve(path, must_exist=False)
        encoded = content.encode("utf-8")
        if len(encoded) > self._config.max_file_bytes:
            msg = (
                f"Refusing to write {len(encoded)} bytes to {path}: exceeds the "
                f"{self._config.max_file_bytes}-byte limit."
            )
            raise ValueError(msg)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        return f"Wrote {len(encoded)} bytes to {self._relative(target)}"

    def edit_file(self, path: str, find: str, replace: str) -> str:
        """Replace one exact occurrence of `find` with `replace` in a workspace file.

        Args:
            path: Path relative to the workspace root.
            find: Literal text to look for. Must match exactly once in the file.
            replace: Text to substitute in.

        Returns:
            A confirmation message describing how many bytes changed.
        """
        if not find:
            msg = "edit_file requires a non-empty `find` string."
            raise ValueError(msg)
        target = self._resolve(path)
        text = target.read_text(encoding="utf-8")
        occurrences = text.count(find)
        if occurrences == 0:
            msg = f"`find` was not found in {path}."
            raise ValueError(msg)
        if occurrences > 1:
            msg = (
                f"`find` matched {occurrences} times in {path}. Provide enough surrounding "
                f"context so the match is unique."
            )
            raise ValueError(msg)
        new_text = text.replace(find, replace, 1)
        encoded = new_text.encode("utf-8")
        if len(encoded) > self._config.max_file_bytes:
            msg = f"Edit would push {path} over the {self._config.max_file_bytes}-byte limit."
            raise ValueError(msg)
        target.write_text(new_text, encoding="utf-8")
        return f"Edited {self._relative(target)} ({len(find)} -> {len(replace)} bytes)"

    def glob_files(self, pattern: str) -> list[str]:
        """Return workspace-relative paths matching a glob pattern.

        Args:
            pattern: Glob pattern, e.g. ``"src/**/*.py"``. Recursive globs are
                supported via ``**``. Hidden files and directories are excluded.

        Returns:
            Up to a few hundred matches as workspace-relative POSIX paths.
        """
        results: list[str] = []
        for path in self._root.glob(pattern):
            if any(part.startswith(".") for part in path.relative_to(self._root).parts):
                continue
            if not self._within_root(path):
                continue
            if path.is_file():
                results.append(self._relative(path))
            if len(results) >= DEFAULT_MAX_GLOB_MATCHES:
                break
        return results

    def grep_files(self, regex: str, glob: str = "**/*") -> list[str]:
        """Search the workspace for lines matching a regex.

        Args:
            regex: Python regular expression to search for.
            glob: Glob pattern that limits which files are searched. Defaults
                to every regular file under the workspace.

        Returns:
            Match lines formatted as ``relative_path:line_number:line_text``.
            Capped at a couple hundred matches.
        """
        try:
            compiled = re.compile(regex)
        except re.error as exc:
            msg = f"Invalid regex {regex!r}: {exc}"
            raise ValueError(msg) from exc
        results: list[str] = []
        for path in self._root.glob(glob):
            if not path.is_file():
                continue
            if any(part.startswith(".") for part in path.relative_to(self._root).parts):
                continue
            if not self._within_root(path):
                continue
            try:
                with path.open(encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if compiled.search(line):
                            results.append(f"{self._relative(path)}:{lineno}:{line.rstrip()}")
                            if len(results) >= DEFAULT_MAX_GREP_MATCHES:
                                return results
            except OSError:
                continue
        return results

    async def shell(self, command: str) -> str:
        """Run a shell command inside the workspace and return its combined output.

        The command runs with the workspace as its working directory, with the
        platform shell, and is killed if it exceeds the configured timeout.
        Allow/deny lists from the toolset config gate which commands are even
        attempted.

        Args:
            command: The full shell command line to execute.

        Returns:
            A string starting with ``exit_code=N`` followed by the combined
            stdout / stderr output, truncated at the configured byte cap.
        """
        if not self._config.shell_enabled:
            msg = "Shell access is disabled in this workspace."
            raise PermissionError(msg)
        head = (command.strip().split(maxsplit=1) or [""])[0]
        if self._config.shell_allowlist and head not in self._config.shell_allowlist:
            msg = f"Command {head!r} is not in the allowlist."
            raise PermissionError(msg)
        if head in self._config.shell_denylist:
            msg = f"Command {head!r} is on the denylist."
            raise PermissionError(msg)

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self._root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        try:
            output_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=self._config.shell_timeout_seconds)
        except TimeoutError:
            msg = f"Shell command timed out after {self._config.shell_timeout_seconds:g} seconds: {command}"
            raise TimeoutError(msg) from None
        finally:
            # Never let the subprocess outlive this tool call. A timeout or a
            # cancelled agent run raises out of `communicate`, so without this
            # an orphaned process would keep running in the workspace.
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                    await proc.wait()

        cap = self._config.max_shell_output_bytes
        truncated = len(output_bytes) > cap
        body = output_bytes[:cap].decode("utf-8", errors="replace")
        if truncated:
            body += f"\n\n[truncated at {cap} bytes]"
        return f"exit_code={proc.returncode}\n{body}"

    def _resolve(self, path: str, *, must_exist: bool = True) -> Path:
        if not path:
            msg = "Path cannot be empty."
            raise ValueError(msg)
        # Reject absolute paths outside root, escape sequences, and symlinks
        # that resolve outside the workspace. `canonicalize_for_identity`
        # follows symlinks, so the containment check below cannot be bypassed
        # by a link that lives inside the root but points elsewhere.
        candidate = canonicalize_for_identity(path, base=self._root)
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            msg = f"Path {path!r} resolves to {candidate}, which is outside the workspace."
            raise PermissionError(msg) from exc
        if must_exist and not candidate.exists():
            msg = f"File not found: {path}"
            raise FileNotFoundError(msg)
        return candidate

    def _relative(self, path: Path) -> str:
        return path.relative_to(self._root).as_posix()

    def _within_root(self, path: Path) -> bool:
        """True when `path` stays inside the workspace after resolving symlinks.

        ``glob`` returns paths spelled under the root, but a symlink inside the
        root can still point outside it. Resolving symlinks before the
        containment check keeps ``glob_files`` / ``grep_files`` from leaking
        out-of-workspace contents, matching what ``_resolve`` enforces for the
        explicit-path tools.
        """
        try:
            canonicalize_for_identity(path).relative_to(self._root)
        except ValueError:
            return False
        return True


def register_workspace_tools(agent: Agent, config: WorkspaceToolsetConfig) -> WorkspaceToolset:
    """Build a :class:`WorkspaceToolset` and register it on `agent`.

    Returns the toolset so callers can hold a reference (e.g. for tests, or to
    apply the same config to multiple agents).
    """
    toolset = WorkspaceToolset(config)
    toolset.register_on(agent)
    return toolset
