"""Workflow ids: read from file headers, derived for files without one, and settled when two files share one."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from griptape_nodes.files.path_utils import canonicalize_for_identity_preserving_symlinks
from griptape_nodes.node_library.workflow_registry import (
    WorkflowMetadata,
    derive_library_workflow_id,
    derive_workflow_id_for_path,
    read_workflow_metadata,
)
from griptape_nodes.retained_mode.engine import current_engine
from griptape_nodes.retained_mode.events.app_events import (
    AppInitializationComplete,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    ListAllWorkflowsRequest,
    ListAllWorkflowsResultSuccess,
    MoveWorkflowRequest,
    MoveWorkflowResultFailure,
)
from griptape_nodes.retained_mode.managers.library.common import LibraryFitness, LibraryInfo, LibraryLifecycleState

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import ResultPayload


# Fixed workflow ids for files the tests write themselves.
MOVER_ID = "00000000000000000000000000000001"
STALE_ID = "00000000000000000000000000000002"
SHARED_ID = "00000000000000000000000000000004"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """An empty workspace folder, links resolved so paths compare as the registry stores them."""
    workspace = tmp_path.resolve() / "workspace"
    workspace.mkdir()
    return workspace


def _run(engine: Engine, request: object) -> ResultPayload:
    return asyncio.run(engine.ahandle_request(request))  # type: ignore[arg-type]


def _header_id(path: str | Path) -> str | None:
    return read_workflow_metadata(Path(path)).workflow_id


def _write_workflow_file(path: Path, *, workflow_id: str | None, name: str = "flow") -> Path:
    """Write a workflow file carrying only a metadata header."""
    metadata = WorkflowMetadata(
        workflow_id=workflow_id,
        name=name,
        schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
        engine_version_created_with="0.0.0",
        node_libraries_referenced=[],
    )
    lines = ["# /// script", "# dependencies = []", "#", "# [tool.griptape-nodes]"]
    for key, value in metadata.model_dump(exclude_none=True, mode="json").items():
        if isinstance(value, str):
            lines.append(f'# {key} = "{value}"')
        elif isinstance(value, bool):
            lines.append(f"# {key} = {str(value).lower()}")
        elif isinstance(value, list):
            lines.append(f"# {key} = []")
    lines.extend(["# ///", "", "print('body')", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _scan(engine: Engine, *paths: Path) -> None:
    """Refresh the registry from just these folders or files."""
    asyncio.run(engine.workflow_manager.refresh_workflow_registry(workflows_to_register=[str(p) for p in paths]))


class TestWorkflowIdHeader:
    def test_header_round_trips_the_id(self, tmp_path: Path) -> None:
        engine = current_engine()
        metadata = WorkflowMetadata(
            workflow_id="0123456789abcdef0123456789abcdef",
            name="flow",
            schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
            engine_version_created_with="0.0.0",
            node_libraries_referenced=[],
        )
        header = engine.workflow_manager.codegen._generate_workflow_metadata_header(metadata)
        assert header is not None
        workflow_file = tmp_path / "flow.py"
        workflow_file.write_text(f"{header}\n\nprint('body')\n", encoding="utf-8")

        read_back = read_workflow_metadata(workflow_file)

        assert read_back.workflow_id == "0123456789abcdef0123456789abcdef"
        assert read_back.schema_version == "0.22.0"

    def test_header_without_an_id_parses(self, tmp_path: Path) -> None:
        workflow_file = _write_workflow_file(tmp_path / "old.py", workflow_id=None)

        assert read_workflow_metadata(workflow_file).workflow_id is None

    def test_malformed_id_is_treated_as_absent(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        workflow_file = _write_workflow_file(tmp_path / "bad.py", workflow_id=None)
        content = workflow_file.read_text(encoding="utf-8")
        workflow_file.write_text(
            content.replace("# name = ", '# workflow_id = "not a valid id!"\n# name = '), encoding="utf-8"
        )

        with caplog.at_level(logging.WARNING, logger="griptape_nodes"):
            metadata = read_workflow_metadata(workflow_file)

        assert metadata.workflow_id is None
        assert any("malformed workflow_id" in record.getMessage() for record in caplog.records)

    def test_a_dashed_id_is_read_as_its_hex_form(self, tmp_path: Path) -> None:
        dashed = "01234567-89ab-cdef-0123-456789abcdef"
        workflow_file = _write_workflow_file(tmp_path / "dashed.py", workflow_id=None)
        content = workflow_file.read_text(encoding="utf-8")
        workflow_file.write_text(
            content.replace("# name = ", f'# workflow_id = "{dashed}"\n# name = '), encoding="utf-8"
        )

        assert read_workflow_metadata(workflow_file).workflow_id == "0123456789abcdef0123456789abcdef"


class TestDerivedIds:
    def test_derived_ids_name_what_they_are_derived_from(self, tmp_path: Path) -> None:
        """Derived ids are uuid5 names in uuid.NAMESPACE_URL, so tabs that remembered one keep finding it."""
        workflow_file = tmp_path / "flow.py"
        canonical_path = canonicalize_for_identity_preserving_symlinks(workflow_file)

        assert derive_workflow_id_for_path(workflow_file) == (
            uuid.uuid5(uuid.NAMESPACE_URL, f"griptape-nodes:workflow:{canonical_path}").hex
        )
        assert derive_library_workflow_id("My Library", "workflows/demo.py") == "f0ff9161aa0251a8a7e2671abbca8a8d"

    def test_a_file_without_an_id_gets_a_derived_one_that_is_not_written(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        workflow_file = _write_workflow_file(workspace / "legacy.py", workflow_id=None)
        content_before = workflow_file.read_text(encoding="utf-8")

        _scan(engine, workspace)

        entry = engine.workflow_registry.find_by_path(workflow_file)
        assert entry is not None
        assert entry.workflow_id == derive_workflow_id_for_path(workflow_file)
        assert workflow_file.read_text(encoding="utf-8") == content_before

    def test_the_derived_id_is_stable_across_refresh_and_project_switch(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        workflow_file = _write_workflow_file(workspace / "shots" / "legacy.py", workflow_id=None)
        _scan(engine, workspace)
        first_id = engine.workflow_registry.find_by_path(workflow_file).workflow_id  # type: ignore[union-attr]

        _scan(engine, workspace)
        after_refresh = engine.workflow_registry.find_by_path(workflow_file)
        engine.config_manager.workspace_path = workspace / "shots"
        _scan(engine, workspace / "shots")
        after_switch = engine.workflow_registry.find_by_path(workflow_file)

        assert after_refresh is not None
        assert after_switch is not None
        assert after_refresh.workflow_id == first_id
        assert after_switch.workflow_id == first_id
        assert after_switch.name == "legacy"

    def test_a_library_workflow_id_survives_the_library_moving(self, tmp_path: Path) -> None:
        """Derived from the library's name and the path inside it, so a reinstall elsewhere keeps it."""
        engine = current_engine()
        first_root = tmp_path / "install_a" / "my_library"
        second_root = tmp_path / "install_b" / "my_library"
        for root in (first_root, second_root):
            _write_workflow_file(root / "workflows" / "demo.py", workflow_id=None)
            (root / "griptape_nodes_library.json").write_text("{}")

        ids = []
        for root in (first_root, second_root):
            library_info = LibraryInfo(
                lifecycle_state=LibraryLifecycleState.LOADED,
                fitness=LibraryFitness.GOOD,
                library_path=str(root / "griptape_nodes_library.json"),
                is_sandbox=False,
                library_name="My Library",
            )
            with patch.dict(engine.library_manager._library_file_path_to_info, {"lib": library_info}, clear=True):
                workflow_file = root / "workflows" / "demo.py"
                workflow = engine.workflow_manager.identity.register_file(
                    workflow_file, read_workflow_metadata(workflow_file)
                )
                ids.append(workflow.workflow_id)
                engine.workflow_registry.remove(workflow.workflow_id)

        assert ids[0] == ids[1] == derive_library_workflow_id("My Library", "workflows/demo.py")


class TestDuplicateIds:
    """A copy of a stamped file is settled once: one file keeps the id, the other is restamped."""

    def test_the_copy_is_restamped_at_detection(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        original = _write_workflow_file(workspace / "original.py", workflow_id=SHARED_ID)
        copy = workspace / "copy.py"
        shutil.copy(original, copy)
        birth_times = {original: 1.0, copy: 2.0}

        with patch(
            "griptape_nodes.retained_mode.managers.workflow.identity.file_birth_time",
            side_effect=lambda path: birth_times[path],
        ):
            _scan(engine, workspace)

        copy_id = _header_id(copy)
        assert _header_id(original) == SHARED_ID
        assert copy_id not in (None, SHARED_ID)
        assert engine.workflow_registry.find_by_path(original).workflow_id == SHARED_ID  # type: ignore[union-attr]
        assert engine.workflow_registry.find_by_path(copy).workflow_id == copy_id  # type: ignore[union-attr]

        # Settled: the next scan finds two different ids and writes nothing.
        _scan(engine, workspace)
        assert _header_id(copy) == copy_id

    def test_without_birth_times_the_smallest_path_keeps_the_id(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        first = _write_workflow_file(workspace / "a.py", workflow_id=SHARED_ID)
        second = workspace / "b.py"
        shutil.copy(first, second)

        with patch("griptape_nodes.retained_mode.managers.workflow.identity.file_birth_time", return_value=None):
            _scan(engine, workspace)

        assert _header_id(first) == SHARED_ID
        assert _header_id(second) != SHARED_ID

    def test_on_refresh_the_file_that_had_the_id_keeps_it(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        original = _write_workflow_file(workspace / "z_original.py", workflow_id=SHARED_ID)
        _scan(engine, workspace)
        copy = workspace / "a_copy.py"
        shutil.copy(original, copy)

        # The copy looks older and sorts first, so only the refresh rule keeps the id on the original.
        birth_times = {original: 2.0, copy: 1.0}
        with patch(
            "griptape_nodes.retained_mode.managers.workflow.identity.file_birth_time",
            side_effect=lambda path: birth_times[path],
        ):
            _scan(engine, workspace)

        assert _header_id(original) == SHARED_ID
        assert _header_id(copy) != SHARED_ID

    @pytest.mark.parametrize(
        "initialization",
        [
            pytest.param(AppInitializationComplete(skip_library_loading=True, is_worker=True), id="worker"),
            pytest.param(
                AppInitializationComplete(skip_library_loading=True, defer_pending_library_resets=True),
                id="beside-an-orchestrator",
            ),
        ],
    )
    def test_an_engine_that_does_not_own_the_workspace_never_restamps(
        self, workspace: Path, initialization: AppInitializationComplete
    ) -> None:
        """Workers and short-lived engines scan the same workspace; only its owner writes, so ids cannot drift."""
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        # Headless initialization registers secrets, which writes the user's real `.env`.
        with patch.object(engine.secrets_manager, "register_all_secrets"):
            asyncio.run(engine.library_manager._run_app_initialization(initialization))
        assert engine.library_manager.owns_workspace is False
        original = _write_workflow_file(workspace / "a.py", workflow_id=SHARED_ID)
        copy = workspace / "b.py"
        shutil.copy(original, copy)
        copy_content = copy.read_text(encoding="utf-8")

        with patch("griptape_nodes.retained_mode.managers.workflow.identity.file_birth_time", return_value=None):
            _scan(engine, workspace)

        assert copy.read_text(encoding="utf-8") == copy_content
        assert _header_id(original) == SHARED_ID
        assert engine.workflow_registry.find_by_path(original).workflow_id == SHARED_ID  # type: ignore[union-attr]
        assert engine.workflow_registry.find_by_path(copy).workflow_id == derive_workflow_id_for_path(copy)  # type: ignore[union-attr]

    @pytest.mark.skipif(os.name == "nt", reason="read-only permission bits are not enforced the same way on Windows")
    def test_engines_that_do_not_own_the_workspace_pick_the_same_winner(self, workspace: Path) -> None:
        """Writability is a property of the file, so a worker and the orchestrator agree on who keeps the id."""
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        writable = _write_workflow_file(workspace / "a.py", workflow_id=SHARED_ID)
        read_only = workspace / "b.py"
        shutil.copy(writable, read_only)
        read_only.chmod(0o444)
        try:
            with (
                patch.object(engine.library_manager, "_owns_workspace", new=False),
                patch("griptape_nodes.retained_mode.managers.workflow.identity.file_birth_time", return_value=None),
            ):
                _scan(engine, workspace)
        finally:
            read_only.chmod(0o644)

        assert engine.workflow_registry.find_by_path(read_only).workflow_id == SHARED_ID  # type: ignore[union-attr]
        assert _header_id(writable) == SHARED_ID

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="symlink creation needs privileges on Windows")
    def test_a_file_reached_through_a_link_is_never_restamped(self, workspace: Path, tmp_path: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        real = _write_workflow_file(tmp_path / "real" / "flow.py", workflow_id=SHARED_ID)
        (workspace / "linked").symlink_to(tmp_path / "real", target_is_directory=True)

        _scan(engine, workspace, real)

        assert _header_id(real) == SHARED_ID
        entry = engine.workflow_registry.get(SHARED_ID)
        assert engine.workflow_registry.find_by_path(workspace / "linked" / "flow.py") is entry
        assert engine.workflow_registry.find_by_path(real) is entry

    @pytest.mark.skipif(os.name == "nt", reason="read-only permission bits are not enforced the same way on Windows")
    def test_a_read_only_loser_gets_the_id_derived_from_its_path(
        self, workspace: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        first = _write_workflow_file(workspace / "a.py", workflow_id=SHARED_ID)
        second = workspace / "b.py"
        shutil.copy(first, second)
        first.chmod(0o444)
        second.chmod(0o444)
        try:
            with (
                patch("griptape_nodes.retained_mode.managers.workflow.identity.file_birth_time", return_value=None),
                caplog.at_level(logging.WARNING, logger="griptape_nodes"),
            ):
                _scan(engine, workspace)
        finally:
            first.chmod(0o644)
            second.chmod(0o644)

        assert _header_id(second) == SHARED_ID
        assert engine.workflow_registry.find_by_path(second).workflow_id == derive_workflow_id_for_path(second)  # type: ignore[union-attr]
        assert any("could not be given a new id" in record.getMessage() for record in caplog.records)

    @pytest.mark.skipif(os.name == "nt", reason="read-only permission bits are not enforced the same way on Windows")
    def test_when_one_file_is_read_only_it_keeps_the_id(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        writable = _write_workflow_file(workspace / "a.py", workflow_id=SHARED_ID)
        read_only = workspace / "b.py"
        shutil.copy(writable, read_only)
        read_only.chmod(0o444)
        try:
            with patch("griptape_nodes.retained_mode.managers.workflow.identity.file_birth_time", return_value=None):
                _scan(engine, workspace)
        finally:
            read_only.chmod(0o644)

        assert _header_id(read_only) == SHARED_ID
        assert _header_id(writable) != SHARED_ID


class TestRegistryRefresh:
    def test_unsaved_workflows_survive_a_refresh(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        unsaved = engine.workflow_registry.register_unsaved("Scratch")

        _scan(engine, workspace)

        assert engine.workflow_registry.get(unsaved.workflow_id) is unsaved
        listing = _run(engine, ListAllWorkflowsRequest())
        assert isinstance(listing, ListAllWorkflowsResultSuccess)
        assert listing.workflows[unsaved.name]["workflow_id"] == unsaved.workflow_id


class TestMoveWorkflow:
    def test_move_onto_a_path_another_entry_holds_puts_the_file_back(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        mover = _write_workflow_file(workspace / "a" / "foo.py", workflow_id=MOVER_ID)
        stale = _write_workflow_file(workspace / "b" / "foo.py", workflow_id=STALE_ID)
        _scan(engine, workspace)
        # Deleted outside the engine: its entry stays until the next scan.
        stale.unlink()

        moved = engine.handle_request(MoveWorkflowRequest(workflow_name="a/foo", target_directory="b"))

        assert isinstance(moved, MoveWorkflowResultFailure)
        assert "Rolled back" in str(moved.result_details)
        assert mover.is_file()
        assert not stale.exists()
        assert engine.workflow_registry.get(MOVER_ID).absolute_path == mover
