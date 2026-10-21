"""Tests for the workflow registry and its `WorkflowRegistry` shim."""

from __future__ import annotations

import logging
import os
import platform
import uuid
from pathlib import Path
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.files.path_utils import derive_registry_key
from griptape_nodes.node_library.workflow_registry import (
    DuplicateWorkflowIdError,
    OpenWorkflowRemovalError,
    UnknownWorkflowAddressError,
    Workflow,
    WorkflowAddressError,
    WorkflowMetadata,
    WorkflowPathTakenError,
    WorkflowRegistry,
    _WorkflowRegistry,
    derive_workflow_id_for_path,
)
from griptape_nodes.retained_mode.engine import (
    Engine,
    current_engine,
    engine_scope,
)

_ID_A = uuid.UUID(int=0xA).hex
_ID_B = uuid.UUID(int=0xB).hex


class TestDeriveRegistryKey:
    def test_flat_workflow(self) -> None:
        assert derive_registry_key("my_workflow.py") == "my_workflow"

    def test_subdirectory(self) -> None:
        assert derive_registry_key("subdir/my_workflow.py") == "subdir/my_workflow"

    def test_nested_subdirectory(self) -> None:
        assert derive_registry_key("a/b/c/my_workflow.py") == "a/b/c/my_workflow"

    def test_backslash_normalization(self) -> None:
        assert derive_registry_key("subdir\\my_workflow.py") == "subdir/my_workflow"

    def test_no_extension(self) -> None:
        assert derive_registry_key("my_workflow") == "my_workflow"

    def test_dot_prefix_normalized(self) -> None:
        assert derive_registry_key("./my_workflow.py") == "my_workflow"

    @pytest.mark.parametrize(
        ("input_path", "expected"),
        [
            ("my_workflow.py", "my_workflow"),
            ("subdir/my_workflow.py", "subdir/my_workflow"),
            ("a/b/deep_workflow.py", "a/b/deep_workflow"),
            ("windows\\path\\workflow.py", "windows/path/workflow"),
            # Case is preserved on every platform.
            ("MyFlow.py", "MyFlow"),
            ("UPPER/MixedCase.py", "UPPER/MixedCase"),
            # Only the final suffix is stripped. `%d.%m_%H.%M` is the engine's own
            # default auto-generated workflow name, so internal dots are common.
            ("03.07_18.30.py", "03.07_18.30"),
            ("subdir/03.07_18.30.py", "subdir/03.07_18.30"),
        ],
    )
    def test_known_inputs(self, input_path: str, expected: str) -> None:
        assert derive_registry_key(input_path) == expected

    def test_not_idempotent_on_dotted_names(self) -> None:
        """Applying the helper to an already-derived dotted key truncates it.

        Callers holding a registry key (e.g. ``ContextManager.get_current_workflow_name()``)
        must compare it directly rather than re-deriving. Pinned so the trap stays visible.
        """
        key = derive_registry_key("03.07_18.30.py")
        assert key == "03.07_18.30"
        assert derive_registry_key(key) == "03.07_18"


class TestGetCompleteFilePath:
    """Tests for resolving registry file paths against the workspace."""

    def test_get_complete_file_path_with_absolute_path(self, engine: Engine) -> None:
        """Test that get_complete_file_path returns absolute paths as-is."""
        # Use a platform-appropriate absolute path
        if os.name == "nt":  # Windows
            absolute_path = "C:\\absolute\\path\\to\\workflow.py"
        else:  # Unix-like
            absolute_path = "/absolute/path/to/workflow.py"

        result = engine.workflow_registry.get_complete_file_path(absolute_path)

        # On Windows, paths starting with / are not considered absolute
        # so they get treated as relative paths
        if os.name == "nt" and absolute_path.startswith("/"):
            # On Windows, Unix-style paths are relative
            assert Path(result).is_absolute()
        else:
            assert result == absolute_path

    def test_get_complete_file_path_with_unix_style_on_windows(self, engine: Engine) -> None:
        """Test Unix-style paths on Windows (treated as relative)."""
        unix_style_path = "/absolute/path/to/workflow.py"
        result = engine.workflow_registry.get_complete_file_path(unix_style_path)

        if os.name == "nt":  # Windows
            # Unix-style paths are treated as relative on Windows
            # The result should be the workspace path + the Unix path
            assert result.endswith("\\absolute\\path\\to\\workflow.py")
            # Verify it's been made absolute
            assert Path(result).is_absolute()
        else:
            # On Unix, this is an absolute path
            assert result == unix_style_path

    def test_get_complete_file_path_with_absolute_windows_path(self, engine: Engine) -> None:
        """Test that get_complete_file_path handles Windows absolute paths."""
        windows_path = "C:\\Users\\test\\workflow.py"

        result = engine.workflow_registry.get_complete_file_path(windows_path)

        # On Windows, it should be returned as-is
        # On Unix systems, Path.is_absolute() returns False for Windows paths,
        # so it will be treated as relative
        if platform.system() == "Windows":
            assert result == windows_path
        else:
            # On Unix, Windows paths are treated as relative
            assert result.endswith("C:\\Users\\test\\workflow.py")

    def test_get_complete_file_path_with_relative_path(self, engine: Engine) -> None:
        """Test that get_complete_file_path resolves relative paths to workspace."""
        relative_path = "workflows/my_workflow.py"

        # Get the actual workspace path from the config manager
        workspace_path = engine.config_manager.workspace_path

        result = engine.workflow_registry.get_complete_file_path(relative_path)

        expected = str(workspace_path / relative_path)
        assert result == expected

    def test_get_complete_file_path_with_home_expansion(self, engine: Engine) -> None:
        """Test that get_complete_file_path handles paths with home directory expansion."""
        home_path = "~/workflows/my_workflow.py"

        # Home paths starting with ~ are NOT considered absolute by Path.is_absolute()
        # so they will be treated as relative paths
        result = engine.workflow_registry.get_complete_file_path(home_path)

        # Should be treated as relative and appended to workspace
        if os.name == "nt":  # Windows
            # On Windows, ~ is just a regular character in the path
            assert result.endswith("~\\workflows\\my_workflow.py")
        else:
            # On Unix, ~ is also treated as relative (not expanded)
            assert result.endswith("~/workflows/my_workflow.py")

    def test_get_complete_file_path_with_current_dir_relative(self, engine: Engine) -> None:
        """Test that get_complete_file_path handles current directory relative paths."""
        current_dir_path = "./my_workflow.py"

        # Get the actual workspace path from the config manager
        workspace_path = engine.config_manager.workspace_path

        result = engine.workflow_registry.get_complete_file_path(current_dir_path)

        expected = str(workspace_path / current_dir_path)
        assert result == expected

    def test_get_complete_file_path_with_parent_dir_relative(self, engine: Engine) -> None:
        """Test that get_complete_file_path handles parent directory relative paths."""
        parent_dir_path = "../external/my_workflow.py"

        # Get the actual workspace path from the config manager
        workspace_path = engine.config_manager.workspace_path

        result = engine.workflow_registry.get_complete_file_path(parent_dir_path)

        # resolve_workspace_path normalizes the path by resolving .. components
        expected = str((workspace_path / parent_dir_path).resolve())
        assert result == expected


def _metadata(name: str = "test", workflow_id: str | None = None) -> WorkflowMetadata:
    return WorkflowMetadata(
        workflow_id=workflow_id,
        name=name,
        schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
        engine_version_created_with="test",
        node_libraries_referenced=[],
    )


def _workflow_id(label: str) -> str:
    """A fixed workflow id for a test, named by `label`."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"test:{label}").hex


def _registry(workspace: Path, *, open_ids: set[str] | None = None) -> _WorkflowRegistry:
    config_manager = MagicMock()
    config_manager.workspace_path = workspace
    open_workflow_ids = open_ids if open_ids is not None else set()
    return _WorkflowRegistry(config_manager, is_workflow_open=lambda workflow_id: workflow_id in open_workflow_ids)


def _workflow_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# stub")
    return path


class TestWorkflowRegistryOperations:
    """Tests for the id-keyed registry and its path and name indexes."""

    def test_register_file_keys_by_the_header_id(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "my_workflow.py")

        workflow = registry.register_file("my_workflow.py", _metadata(workflow_id=_workflow_id("abc123")))

        assert workflow.workflow_id == _workflow_id("abc123")
        assert workflow.metadata.workflow_id == _workflow_id("abc123")
        assert registry.get(_workflow_id("abc123")) is workflow
        assert registry.find_by_name("my_workflow") is workflow
        assert registry.find_by_path(tmp_path / "my_workflow.py") is workflow
        assert workflow.file_path == "my_workflow.py"
        assert workflow.absolute_path == tmp_path / "my_workflow.py"

    def test_register_file_without_an_id_derives_one_from_the_path(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "sub" / "flow.py")

        workflow = registry.register_file("sub/flow.py", _metadata())

        assert workflow.workflow_id == derive_workflow_id_for_path(tmp_path / "sub" / "flow.py")
        assert workflow.metadata.workflow_id == workflow.workflow_id

    def test_register_file_does_not_mutate_the_callers_metadata(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "flow.py")
        metadata = _metadata()

        registry.register_file("flow.py", metadata)

        assert metadata.workflow_id is None

    def test_register_file_requires_the_file(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            _registry(tmp_path).register_file("missing.py", _metadata())

    def test_second_entry_for_a_path_is_refused(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "flow.py")
        registry.register_file("flow.py", _metadata(workflow_id=_workflow_id("first")))

        with pytest.raises(WorkflowPathTakenError):
            registry.register_file(tmp_path / "flow.py", _metadata(workflow_id=_workflow_id("second")))

    def test_refused_path_names_the_holder_and_changes_nothing(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "flow.py")
        holder = registry.register_file("flow.py", _metadata(workflow_id=_workflow_id("first")))

        with pytest.raises(WorkflowPathTakenError) as raised:
            registry.register_file("flow.py", _metadata(workflow_id=_workflow_id("second")))

        assert raised.value.existing is holder
        assert registry.find_by_id(_workflow_id("second")) is None
        assert registry.find_by_path(tmp_path / "flow.py") is holder
        assert list(registry.list_workflows()) == ["flow"]

    def test_refused_name_names_the_holder_and_changes_nothing(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "flow.py")
        _workflow_file(tmp_path / "flow.txt")
        holder = registry.register_file("flow.py", _metadata(workflow_id=_workflow_id("first")))

        with pytest.raises(WorkflowPathTakenError, match="already registered under that name") as raised:
            registry.register_file("flow.txt", _metadata(workflow_id=_workflow_id("second")))

        assert raised.value.existing is holder
        assert registry.find_by_id(_workflow_id("second")) is None
        assert registry.find_by_path(tmp_path / "flow.txt") is None
        assert registry.find_by_name("flow") is holder
        assert list(registry.list_workflows()) == ["flow"]

    def test_same_id_in_another_file_is_a_duplicate(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "original.py")
        _workflow_file(tmp_path / "copy.py")
        original = registry.register_file("original.py", _metadata(workflow_id=_workflow_id("shared")))

        with pytest.raises(DuplicateWorkflowIdError) as raised:
            registry.register_file("copy.py", _metadata(workflow_id=_workflow_id("shared")))

        assert raised.value.existing is original

    @pytest.mark.skipif(platform.system() == "Windows", reason="symlink creation needs privileges on Windows")
    def test_same_file_through_a_link_is_an_alias(self, tmp_path: Path) -> None:
        """A file reached through a link is the same workflow, never a duplicate."""
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "real" / "flow.py")
        (tmp_path / "linked").symlink_to(tmp_path / "real", target_is_directory=True)
        workflow = registry.register_file("real/flow.py", _metadata(workflow_id=_workflow_id("one")))

        alias = registry.register_file("linked/flow.py", _metadata(workflow_id=_workflow_id("one")))

        assert alias is workflow
        assert registry.find_by_path(tmp_path / "linked" / "flow.py") is workflow
        assert registry.find_by_name("linked/flow") is workflow
        assert list(registry.list_workflows()) == ["real/flow"]

    def test_register_unsaved_names_it_by_its_id(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)

        workflow = registry.register_unsaved("Untitled", str(tmp_path / "shots"))

        assert workflow.name == f"unsaved:{workflow.workflow_id}"
        assert workflow.file_path is None
        assert workflow.absolute_path is None
        assert workflow.working_directory == str(tmp_path / "shots")
        assert workflow.metadata.name == "Untitled"
        assert registry.find_by_name(workflow.name) is workflow

    def test_register_unsaved_refuses_an_id_another_entry_has(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        existing = registry.register_unsaved("First", workflow_id=_workflow_id("taken"))

        with pytest.raises(DuplicateWorkflowIdError) as raised:
            registry.register_unsaved("Second", workflow_id=_workflow_id("taken"))

        assert raised.value.existing is existing
        assert registry.get(_workflow_id("taken")) is existing
        assert list(registry.list_workflows()) == [existing.name]

    def test_find_by_name_accepts_a_dashed_unsaved_name(self, tmp_path: Path) -> None:
        """Earlier engines minted "unsaved:<uuid>" with dashes; it names the same workflow as the hex form."""
        registry = _registry(tmp_path)
        workflow = registry.register_unsaved("Untitled", workflow_id="0123456789abcdef0123456789abcdef")

        assert registry.find_by_name("unsaved:01234567-89ab-cdef-0123-456789abcdef") is workflow
        assert registry.has_workflow_with_name("unsaved:01234567-89ab-cdef-0123-456789abcdef")
        assert registry.find_by_name("unsaved:not-an-id") is None

    def test_set_file_path_reindexes_and_keeps_the_id(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "old.py")
        _workflow_file(tmp_path / "moved" / "new.py")
        workflow = registry.register_file("old.py", _metadata(workflow_id=_workflow_id("keep")))

        registry.set_file_path(workflow, "moved/new.py")

        assert workflow.workflow_id == _workflow_id("keep")
        assert workflow.name == "moved/new"
        assert workflow.file_path == str(Path("moved") / "new.py")
        assert registry.find_by_name("moved/new") is workflow
        assert registry.find_by_name("old") is None
        assert registry.find_by_path(tmp_path / "old.py") is None
        assert registry.find_by_path(tmp_path / "moved" / "new.py") is workflow

    def test_set_file_path_saves_an_unsaved_workflow(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        workflow = registry.register_unsaved("Untitled")
        unsaved_name = workflow.name
        _workflow_file(tmp_path / "saved.py")

        registry.set_file_path(workflow, tmp_path / "saved.py")

        assert workflow.is_saved
        assert workflow.name == "saved"
        assert registry.find_by_name(unsaved_name) is None
        assert registry.get(workflow.workflow_id) is workflow

    def test_set_file_path_refuses_a_path_another_entry_holds(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "a.py")
        _workflow_file(tmp_path / "b.py")
        first = registry.register_file("a.py", _metadata(workflow_id=_workflow_id("a")))
        registry.register_file("b.py", _metadata(workflow_id=_workflow_id("b")))

        with pytest.raises(WorkflowPathTakenError):
            registry.set_file_path(first, "b.py")

        assert first.name == "a"
        assert registry.find_by_name("a") is first

    def test_set_file_path_restores_the_entry_when_the_new_name_is_taken(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "a.py")
        _workflow_file(tmp_path / "b.py")
        _workflow_file(tmp_path / "b.txt")
        first = registry.register_file("a.py", _metadata(workflow_id=_workflow_id("a")))
        holder = registry.register_file("b.py", _metadata(workflow_id=_workflow_id("b")))

        with pytest.raises(WorkflowPathTakenError) as raised:
            registry.set_file_path(first, "b.txt")

        assert raised.value.existing is holder
        assert first.absolute_path == tmp_path / "a.py"
        assert first.file_path == "a.py"
        assert first.name == "a"
        assert registry.find_by_path(tmp_path / "a.py") is first
        assert registry.find_by_path(tmp_path / "b.txt") is None
        assert registry.find_by_name("a") is first
        assert registry.find_by_name("b") is holder

    @pytest.mark.skipif(platform.system() == "Windows", reason="symlink creation needs privileges on Windows")
    def test_set_file_path_restores_the_aliases_when_the_new_name_is_taken(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "real" / "flow.py")
        _workflow_file(tmp_path / "b.py")
        _workflow_file(tmp_path / "b.txt")
        (tmp_path / "linked").symlink_to(tmp_path / "real", target_is_directory=True)
        workflow = registry.register_file("real/flow.py", _metadata(workflow_id=_workflow_id("one")))
        registry.register_file("linked/flow.py", _metadata(workflow_id=_workflow_id("one")))
        registry.register_file("b.py", _metadata(workflow_id=_workflow_id("b")))
        known_paths = workflow.known_paths

        with pytest.raises(WorkflowPathTakenError):
            registry.set_file_path(workflow, "b.txt")

        assert workflow.known_paths == known_paths
        assert tmp_path / "linked" / "flow.py" in known_paths
        assert registry.find_by_path(tmp_path / "linked" / "flow.py") is workflow
        assert registry.find_by_name("linked/flow") is workflow
        assert registry.find_by_name("real/flow") is workflow

    def test_set_file_path_refuses_an_unregistered_workflow(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "flow.py")
        stranger = Workflow(workflow_id=_workflow_id("stranger"), metadata=_metadata(), absolute_path=None)

        with pytest.raises(KeyError, match="not registered"):
            registry.set_file_path(stranger, "flow.py")

        assert registry.find_by_path(tmp_path / "flow.py") is None

    def test_set_file_path_requires_the_file(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        workflow = registry.register_unsaved("Untitled")

        with pytest.raises(ValueError, match="does not exist"):
            registry.set_file_path(workflow, "missing.py")

        assert not workflow.is_saved
        assert registry.find_by_name(workflow.name) is workflow

    def test_remove_refuses_an_open_workflow(self, tmp_path: Path) -> None:
        open_ids: set[str] = set()
        registry = _registry(tmp_path, open_ids=open_ids)
        workflow = registry.register_unsaved("Open")
        open_ids.add(workflow.workflow_id)

        with pytest.raises(OpenWorkflowRemovalError):
            registry.remove(workflow.workflow_id)

        assert registry.get(workflow.workflow_id) is workflow

    def test_remove_drops_every_index(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "flow.py")
        workflow = registry.register_file("flow.py", _metadata(workflow_id=_workflow_id("gone")))

        removed = registry.remove(_workflow_id("gone"))

        assert removed is workflow

        assert registry.find_by_name("flow") is None
        assert registry.find_by_path(tmp_path / "flow.py") is None
        with pytest.raises(KeyError, match="no workflow has that id"):
            registry.get(_workflow_id("gone"))

    def test_clear_saved_workflows_keeps_unsaved_and_open_entries(self, tmp_path: Path) -> None:
        """A refresh drops saved entries to rescan them, but keeps what a rescan cannot find again."""
        open_ids: set[str] = set()
        registry = _registry(tmp_path, open_ids=open_ids)
        _workflow_file(tmp_path / "closed.py")
        _workflow_file(tmp_path / "open.py")
        closed = registry.register_file("closed.py", _metadata(workflow_id=_workflow_id("closed")))
        opened = registry.register_file("open.py", _metadata(workflow_id=_workflow_id("open")))
        unsaved = registry.register_unsaved("Scratch")
        open_ids.add(opened.workflow_id)

        previous_paths = registry.clear_saved_workflows()

        assert previous_paths == {_workflow_id("closed"): closed.absolute_path}
        assert registry.find_by_name("closed") is None
        assert registry.find_by_name("open") is opened
        assert registry.find_by_name(unsaved.name) is unsaved

    def test_clear_saved_workflows_renames_kept_entries_for_a_new_workspace(self, tmp_path: Path) -> None:
        """A kept entry's name is derived again against the workspace a project switch moved to."""
        open_ids: set[str] = set()
        registry = _registry(tmp_path / "ws", open_ids=open_ids)
        _workflow_file(tmp_path / "ws" / "shots" / "flow.py")
        opened = registry.register_file("shots/flow.py", _metadata(workflow_id=_workflow_id("open")))
        open_ids.add(opened.workflow_id)

        registry._config_manager.workspace_path = tmp_path / "ws" / "shots"
        registry.clear_saved_workflows()

        assert opened.name == "flow"
        assert registry.find_by_name("flow") is opened
        assert registry.find_by_name("shots/flow") is None

    def test_unlisted_entries_are_left_out_of_the_list(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "opened.py")
        workflow = registry.register_file("opened.py", _metadata(), listed=False)

        assert registry.list_workflows() == {}
        assert registry.find_by_name("opened") is workflow

    def test_listed_entries_carry_their_id(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        workflow = registry.register_unsaved("Untitled")

        listing = registry.list_workflows()

        assert listing[workflow.name]["workflow_id"] == workflow.workflow_id

    def test_metadata_without_an_id_inherits_the_workflows(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        workflow = registry.register_unsaved("Untitled")

        workflow.metadata = _metadata("Renamed")

        assert workflow.metadata.workflow_id == workflow.workflow_id
        assert workflow.metadata.name == "Renamed"

    def test_metadata_with_another_id_is_refused(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        workflow = registry.register_unsaved("Untitled")

        with pytest.raises(ValueError, match="never changes"):
            workflow.metadata = _metadata(workflow_id=_workflow_id("someone_else"))

        assert workflow.metadata.name == "Untitled"

    def test_engines_do_not_share_workflows(self, engine: Engine) -> None:
        other = Engine()

        workflow = engine.workflow_registry.register_unsaved("Mine")

        assert engine.workflow_registry.has_workflow_with_name(workflow.name)
        assert not other.workflow_registry.has_workflow_with_name(workflow.name)


class _TwoWorkflows(NamedTuple):
    registry: _WorkflowRegistry
    shot_a: Workflow
    shot_b: Workflow


class TestResolveAddress:
    """`resolve_address` turns a request's id and legacy name into one entry, and never picks."""

    def _two_workflows(self, tmp_path: Path) -> _TwoWorkflows:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "shot_a.py")
        _workflow_file(tmp_path / "shot_b.py")
        shot_a = registry.register_file("shot_a.py", _metadata(workflow_id=_ID_A))
        shot_b = registry.register_file("shot_b.py", _metadata(workflow_id=_ID_B))
        return _TwoWorkflows(registry=registry, shot_a=shot_a, shot_b=shot_b)

    def test_id_alone_finds_its_workflow(self, tmp_path: Path) -> None:
        registry, _shot_a, shot_b = self._two_workflows(tmp_path)

        assert registry.resolve_address(workflow_id=_ID_B, workflow_name=None, operation="rename") is shot_b

    def test_name_alone_finds_its_workflow_and_logs_at_debug(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        registry, shot_a, _shot_b = self._two_workflows(tmp_path)

        with caplog.at_level(logging.DEBUG, logger="griptape_nodes"):
            resolved = registry.resolve_address(workflow_id=None, workflow_name="shot_a", operation="rename")

        assert resolved is shot_a
        records = [record for record in caplog.records if "by workflow_name" in record.getMessage()]
        assert [record.levelno for record in records] == [logging.DEBUG]

    def test_unsaved_name_finds_the_unsaved_workflow(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        unsaved = registry.register_unsaved("Untitled")

        resolved = registry.resolve_address(workflow_id=None, workflow_name=unsaved.name, operation="delete")

        assert resolved is unsaved

    def test_id_and_name_of_the_same_workflow_agree(self, tmp_path: Path) -> None:
        registry, shot_a, _shot_b = self._two_workflows(tmp_path)

        resolved = registry.resolve_address(workflow_id=_ID_A, workflow_name="shot_a", operation="rename")

        assert resolved is shot_a

    def test_id_and_name_of_different_workflows_fail_naming_both(self, tmp_path: Path) -> None:
        registry, _shot_a, _shot_b = self._two_workflows(tmp_path)

        with pytest.raises(WorkflowAddressError) as raised:
            registry.resolve_address(workflow_id=_ID_A, workflow_name="shot_b", operation="rename")

        assert not isinstance(raised.value, UnknownWorkflowAddressError)
        message = str(raised.value)
        assert message.startswith(f"Attempted to rename workflow '{_ID_A}'.")
        assert "'shot_a'" in message
        assert "'shot_b'" in message
        assert _ID_B in message

    def test_id_with_an_unknown_name_fails(self, tmp_path: Path) -> None:
        registry, _shot_a, _shot_b = self._two_workflows(tmp_path)

        with pytest.raises(WorkflowAddressError, match="names no workflow"):
            registry.resolve_address(workflow_id=_ID_A, workflow_name="missing", operation="move")

    def test_neither_fails_asking_for_the_id(self, tmp_path: Path) -> None:
        registry, _shot_a, _shot_b = self._two_workflows(tmp_path)

        with pytest.raises(WorkflowAddressError) as raised:
            registry.resolve_address(
                workflow_id=None,
                workflow_name=None,
                operation="create a workflow from",
                id_field="template_workflow_id",
            )

        assert not isinstance(raised.value, UnknownWorkflowAddressError)
        assert str(raised.value) == (
            "Attempted to create a workflow from a workflow. Failed because the request names no workflow. "
            "Pass template_workflow_id."
        )

    def test_unknown_id_fails(self, tmp_path: Path) -> None:
        registry, _shot_a, _shot_b = self._two_workflows(tmp_path)

        with pytest.raises(UnknownWorkflowAddressError) as raised:
            registry.resolve_address(workflow_id="id_missing", workflow_name=None, operation="delete")

        assert str(raised.value) == "Attempted to delete workflow 'id_missing'. Failed because no workflow has that id."

    def test_unknown_name_fails(self, tmp_path: Path) -> None:
        registry, _shot_a, _shot_b = self._two_workflows(tmp_path)

        with pytest.raises(UnknownWorkflowAddressError) as raised:
            registry.resolve_address(workflow_id=None, workflow_name="missing", operation="delete")

        assert str(raised.value) == "Attempted to delete workflow 'missing'. Failed because no workflow has that name."

    def test_display_name_is_never_an_address(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "shot_a.py")
        registry.register_file("shot_a.py", _metadata(name="Shot A", workflow_id=_ID_A))

        with pytest.raises(UnknownWorkflowAddressError):
            registry.resolve_address(workflow_id=None, workflow_name="Shot A", operation="open")

    def test_dashed_spellings_of_an_id_name_the_same_workflow(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        unsaved = registry.register_unsaved("Untitled")
        dashed_id = str(uuid.UUID(hex=unsaved.workflow_id))

        by_name = registry.resolve_address(workflow_id=None, workflow_name=f"unsaved:{dashed_id}", operation="open")
        by_id = registry.resolve_address(workflow_id=dashed_id, workflow_name=None, operation="open")

        assert by_name is unsaved
        assert by_id is unsaved

    def test_an_id_that_is_not_a_uuid_names_no_workflow(self, tmp_path: Path) -> None:
        registry, _shot_a, _shot_b = self._two_workflows(tmp_path)

        with pytest.raises(UnknownWorkflowAddressError):
            registry.resolve_address(workflow_id="not-a-uuid", workflow_name=None, operation="open")


class TestWorkflowRegistryShim:
    """`WorkflowRegistry` classmethods act on the current engine's registry."""

    def test_reads_what_the_engine_registered(self, engine: Engine) -> None:
        workflow = engine.workflow_registry.register_unsaved("Untitled")

        assert WorkflowRegistry.has_workflow_with_name(workflow.name)
        assert WorkflowRegistry.get_workflow_by_name(workflow.name) is workflow

    def test_follows_the_scoped_engine(self) -> None:
        root = current_engine()

        with engine_scope() as scoped:
            workflow = scoped.workflow_registry.register_unsaved("Scoped")
            assert WorkflowRegistry.has_workflow_with_name(workflow.name)

        assert not root.workflow_registry.has_workflow_with_name(workflow.name)

    def test_unsaved_key_prefix_matches(self) -> None:
        assert WorkflowRegistry.UNSAVED_KEY_PREFIX == _WorkflowRegistry.UNSAVED_KEY_PREFIX


class TestGetWorkflowMetadata:
    """`Workflow.get_workflow_metadata` and the `is_synced` flag `list_workflows` gives it."""

    def test_reports_the_given_is_synced_and_the_entry_fields(self) -> None:
        workflow = Workflow(workflow_id=_workflow_id("test"), metadata=_metadata("Test"), absolute_path=None)

        result = workflow.get_workflow_metadata(is_synced=True)

        assert result["is_synced"] is True
        assert result["workflow_id"] == _workflow_id("test")
        assert result["file_path"] is None
        assert result["is_saved"] is False

    def test_list_workflows_marks_files_in_the_synced_directory(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        _workflow_file(tmp_path / "synced" / "inside.py")
        _workflow_file(tmp_path / "outside.py")
        registry.register_file("synced/inside.py", _metadata())
        registry.register_file("outside.py", _metadata())
        unsaved = registry.register_unsaved("Scratch")

        with patch.object(registry, "get_synced_workflows_path", return_value=tmp_path / "synced"):
            listed = registry.list_workflows()

        assert listed["synced/inside"]["is_synced"] is True
        assert listed["outside"]["is_synced"] is False
        assert listed[unsaved.name]["is_synced"] is False
