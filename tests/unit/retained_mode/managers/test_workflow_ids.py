"""Workflow ids: written into every file, kept across save, rename, move, refresh and restart."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
from griptape_nodes.files.path_utils import canonicalize_for_identity_preserving_symlinks
from griptape_nodes.node_library.workflow_registry import (
    WorkflowMetadata,
    derive_library_workflow_id,
    derive_workflow_id_for_path,
    read_workflow_metadata,
)
from griptape_nodes.retained_mode.engine import current_engine, reset_root_engine
from griptape_nodes.retained_mode.events.app_events import (
    AppInitializationComplete,
    EngineHeartbeatRequest,
    EngineHeartbeatResultSuccess,
)
from griptape_nodes.retained_mode.events.context_events import (
    EnsureWorkflowAndFlowRequest,
    EnsureWorkflowAndFlowResultSuccess,
    GetWorkflowContextRequest,
    GetWorkflowContextSuccess,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    CreateFlowResultSuccess,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.events.project_events import (
    LoadProjectTemplateRequest,
    LoadProjectTemplateResultSuccess,
    SetCurrentProjectRequest,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    BranchWorkflowRequest,
    BranchWorkflowResultSuccess,
    CreateWorkflowFromTemplateRequest,
    CreateWorkflowFromTemplateResultFailure,
    CreateWorkflowFromTemplateResultSuccess,
    ListAllWorkflowsRequest,
    ListAllWorkflowsResultSuccess,
    MergeWorkflowBranchRequest,
    MergeWorkflowBranchResultFailure,
    MergeWorkflowBranchResultSuccess,
    MoveWorkflowRequest,
    MoveWorkflowResultFailure,
    MoveWorkflowResultSuccess,
    RenameWorkflowRequest,
    RenameWorkflowResultFailure,
    RenameWorkflowResultSuccess,
    ResetWorkflowBranchRequest,
    ResetWorkflowBranchResultFailure,
    ResetWorkflowBranchResultSuccess,
    RunWorkflowFromRegistryRequest,
    RunWorkflowFromRegistryResultSuccess,
    SaveSubflowToWorkflowRequest,
    SaveSubflowToWorkflowResultSuccess,
    SaveWorkflowFileFromSerializedFlowRequest,
    SaveWorkflowRequest,
    SaveWorkflowResultSuccess,
    SetWorkflowMetadataRequest,
    SetWorkflowMetadataResultFailure,
    SetWorkflowMetadataResultSuccess,
)
from griptape_nodes.retained_mode.managers.context_manager import read_metadata_for_open_file
from griptape_nodes.retained_mode.managers.library.common import LibraryFitness, LibraryInfo, LibraryLifecycleState

if TYPE_CHECKING:
    from collections.abc import Generator

    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import ResultPayload


# Fixed workflow ids for files the tests write themselves.
MOVER_ID = "00000000000000000000000000000001"
STALE_ID = "00000000000000000000000000000002"
LINEAGE_ID = "00000000000000000000000000000003"
SHARED_ID = "00000000000000000000000000000004"


def _use_default_project(engine: Engine, workspace: Path) -> None:
    project_yml = workspace / "project_template.yml"
    project_yml.write_text(DEFAULT_PROJECT_TEMPLATE.to_overlay_yaml(DEFAULT_PROJECT_TEMPLATE))
    load_result = engine.handle_request(LoadProjectTemplateRequest(project_path=project_yml))
    assert isinstance(load_result, LoadProjectTemplateResultSuccess)
    engine.handle_request(SetCurrentProjectRequest(project_id=load_result.project_id))
    engine.config_manager.workspace_path = workspace


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """An empty workspace folder, links resolved so paths compare as the registry stores them."""
    workspace = tmp_path.resolve() / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def project_engine(workspace: Path) -> Generator[Engine, None, None]:
    """The current engine on the default project, with `workspace` as its workspace."""
    engine = current_engine()
    _use_default_project(engine, workspace)
    yield engine
    current_engine().handle_request(SetCurrentProjectRequest(project_id=None))


def _run(engine: Engine, request: object) -> ResultPayload:
    return asyncio.run(engine.ahandle_request(request))  # type: ignore[arg-type]


def _open_new_workflow(engine: Engine, display_name: str) -> str:
    result = engine.handle_request(EnsureWorkflowAndFlowRequest(display_name=display_name))
    assert isinstance(result, EnsureWorkflowAndFlowResultSuccess), result.result_details
    assert result.workflow_id is not None
    return result.workflow_id


def _save(engine: Engine, request: SaveWorkflowRequest | None = None) -> SaveWorkflowResultSuccess:
    result = _run(engine, request or SaveWorkflowRequest())
    assert isinstance(result, SaveWorkflowResultSuccess), result.result_details
    return result


def _close(engine: Engine) -> None:
    engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))


def _saved_workflow(engine: Engine, display_name: str) -> SaveWorkflowResultSuccess:
    """Create, save and close a workflow; return its save result."""
    _open_new_workflow(engine, display_name)
    saved = _save(engine)
    _close(engine)
    return saved


def _listed(engine: Engine) -> dict[str, dict]:
    listing = _run(engine, ListAllWorkflowsRequest())
    assert isinstance(listing, ListAllWorkflowsResultSuccess)
    return listing.workflows


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

    def test_both_header_writers_refuse_a_missing_id(self) -> None:
        codegen = current_engine().workflow_manager.codegen
        metadata = WorkflowMetadata(
            name="flow",
            schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
            engine_version_created_with="0.0.0",
            node_libraries_referenced=[],
        )

        with pytest.raises(ValueError, match="no workflow id"):
            codegen._generate_workflow_metadata_header(metadata)
        with pytest.raises(ValueError, match="no workflow id"):
            codegen.replace_workflow_metadata_header("# /// script\n# ///\n", metadata)


class TestWritePathsStampAnId:
    """Every write path puts an id in the file: the lineage's own, or a new one for a copy."""

    def test_first_save_writes_the_unsaved_workflows_id(self, project_engine: Engine) -> None:
        workflow_id = _open_new_workflow(project_engine, "first")

        saved = _save(project_engine)

        assert saved.workflow_id == workflow_id
        assert _header_id(saved.file_path) == workflow_id
        assert project_engine.context_manager.get_current_workflow_id() == workflow_id

    def test_saving_again_keeps_the_id(self, project_engine: Engine) -> None:
        workflow_id = _open_new_workflow(project_engine, "again")
        first = _save(project_engine)

        second = _save(project_engine, SaveWorkflowRequest(file_name=first.workflow_name))

        assert second.file_path == first.file_path
        assert second.workflow_id == workflow_id
        assert _header_id(second.file_path) == workflow_id

    def test_save_as_writes_a_copy_with_a_new_id(self, project_engine: Engine) -> None:
        workflow_id = _open_new_workflow(project_engine, "original")
        _save(project_engine)

        copy = _save(project_engine, SaveWorkflowRequest(file_name="the_copy"))

        assert copy.workflow_id != workflow_id
        assert _header_id(copy.file_path) == copy.workflow_id
        # The open workflow stays on the original.
        assert project_engine.context_manager.get_current_workflow_id() == workflow_id
        assert project_engine.workflow_registry.find_by_name("the_copy").workflow_id == copy.workflow_id  # type: ignore[union-attr]

    def test_versioned_save_writes_a_copy_with_a_new_id(self, project_engine: Engine) -> None:
        workflow_id = _open_new_workflow(project_engine, "versioned")
        _save(project_engine)

        version = _save(project_engine, SaveWorkflowRequest(create_versioned=True))

        assert version.workflow_id != workflow_id
        assert _header_id(version.file_path) == version.workflow_id
        assert project_engine.context_manager.get_current_workflow_id() == workflow_id

    def test_first_save_onto_another_workflows_file_takes_it_over(self, project_engine: Engine) -> None:
        """The open workflow keeps its id; the workflow whose file it overwrote ends."""
        other = _saved_workflow(project_engine, "other")
        workflow_id = _open_new_workflow(project_engine, "unsaved")

        saved = _save(project_engine, SaveWorkflowRequest(file_name=other.workflow_name))

        assert saved.file_path == other.file_path
        assert saved.workflow_id == workflow_id
        assert _header_id(saved.file_path) == workflow_id
        assert all(workflow["workflow_id"] != other.workflow_id for workflow in _listed(project_engine).values())
        assert project_engine.workflow_registry.find_by_name(other.workflow_name).workflow_id == workflow_id  # type: ignore[union-attr]

    def test_saving_over_another_saved_workflow_ends_its_identity(self, project_engine: Engine) -> None:
        """A saved workflow saved over another's file is a new workflow there; the open one stays itself."""
        other = _saved_workflow(project_engine, "other")
        workflow_id = _open_new_workflow(project_engine, "mine")
        _save(project_engine)

        written = _save(project_engine, SaveWorkflowRequest(file_name=other.workflow_name))

        assert written.workflow_id not in (workflow_id, other.workflow_id)
        assert _header_id(other.file_path) == written.workflow_id
        assert all(workflow["workflow_id"] != other.workflow_id for workflow in _listed(project_engine).values())
        assert project_engine.context_manager.get_current_workflow_id() == workflow_id

    def test_saving_a_library_workflow_writes_a_copy_with_a_new_id(self, project_engine: Engine) -> None:
        library_id = _open_new_workflow(project_engine, "library_workflow")
        library_saved = _save(project_engine)
        project_engine.workflow_registry.get(library_id).metadata.is_griptape_provided = True

        copy = _save(project_engine, SaveWorkflowRequest(file_name=library_saved.workflow_name))

        assert copy.workflow_id != library_id
        assert _header_id(copy.file_path) == copy.workflow_id
        assert _header_id(library_saved.file_path) == library_id
        # As on main, the open workflow moves onto the copy so the next save lands in it.
        assert project_engine.context_manager.get_current_workflow_id() == copy.workflow_id

    def test_branch_merge_and_reset(self, project_engine: Engine) -> None:
        source = _saved_workflow(project_engine, "source")

        branch = project_engine.handle_request(BranchWorkflowRequest(workflow_name=source.workflow_name))
        assert isinstance(branch, BranchWorkflowResultSuccess), branch.result_details
        assert branch.original_workflow_id == source.workflow_id
        assert branch.branched_workflow_id not in (None, source.workflow_id)
        branch_entry = project_engine.workflow_registry.get(branch.branched_workflow_id)  # type: ignore[arg-type]
        assert _header_id(branch_entry.absolute_path) == branch.branched_workflow_id  # type: ignore[arg-type]

        reset = project_engine.handle_request(ResetWorkflowBranchRequest(workflow_name=branch.branched_workflow_name))
        assert isinstance(reset, ResetWorkflowBranchResultSuccess), reset.result_details
        assert reset.workflow_id == branch.branched_workflow_id
        assert _header_id(branch_entry.absolute_path) == branch.branched_workflow_id  # type: ignore[arg-type]

        merged = project_engine.handle_request(MergeWorkflowBranchRequest(workflow_name=branch.branched_workflow_name))
        assert isinstance(merged, MergeWorkflowBranchResultSuccess), merged.result_details
        assert merged.workflow_id == source.workflow_id
        assert _header_id(source.file_path) == source.workflow_id

    @pytest.mark.parametrize("open_side", ["branch", "source"])
    def test_merging_with_either_side_open_is_refused_before_anything_is_written(
        self, project_engine: Engine, open_side: str
    ) -> None:
        source = _saved_workflow(project_engine, "source")
        branch = project_engine.handle_request(BranchWorkflowRequest(workflow_name=source.workflow_name))
        assert isinstance(branch, BranchWorkflowResultSuccess), branch.result_details
        branch_entry = project_engine.workflow_registry.get(branch.branched_workflow_id)  # type: ignore[arg-type]
        branch_path = branch_entry.absolute_path
        assert branch_path is not None
        source_content = Path(source.file_path).read_text(encoding="utf-8")
        branch_content = branch_path.read_text(encoding="utf-8")
        if open_side == "branch":
            open_id = branch_entry.workflow_id
        else:
            open_id = source.workflow_id
        project_engine.context_manager.push_workflow(workflow_id=open_id)

        merged = project_engine.handle_request(MergeWorkflowBranchRequest(workflow_name=branch.branched_workflow_name))

        assert isinstance(merged, MergeWorkflowBranchResultFailure)
        assert "is open" in str(merged.result_details)
        assert Path(source.file_path).read_text(encoding="utf-8") == source_content
        assert branch_path.read_text(encoding="utf-8") == branch_content
        assert project_engine.workflow_registry.get(branch_entry.workflow_id) is branch_entry
        assert project_engine.context_manager.get_current_workflow_id() == open_id

    def test_create_from_template_gets_a_new_id(self, project_engine: Engine) -> None:
        template = _saved_workflow(project_engine, "template")
        project_engine.workflow_registry.get(template.workflow_id).metadata.is_template = True  # type: ignore[arg-type]

        created = project_engine.handle_request(CreateWorkflowFromTemplateRequest(template_name=template.workflow_name))

        assert isinstance(created, CreateWorkflowFromTemplateResultSuccess), created.result_details
        assert created.workflow_id not in (None, template.workflow_id)
        assert _header_id(created.file_path) == created.workflow_id

    def test_set_metadata_keeps_the_id_and_refuses_a_new_one(self, project_engine: Engine) -> None:
        saved = _saved_workflow(project_engine, "described")

        updated = _run(
            project_engine,
            SetWorkflowMetadataRequest(
                workflow_name=saved.workflow_name,
                workflow_metadata={"description": "now described"},  # type: ignore[arg-type]
            ),
        )
        refused = _run(
            project_engine,
            SetWorkflowMetadataRequest(
                workflow_name=saved.workflow_name,
                workflow_metadata={"workflow_id": "someone_else"},  # type: ignore[arg-type]
            ),
        )

        assert isinstance(updated, SetWorkflowMetadataResultSuccess), updated.result_details
        assert read_workflow_metadata(Path(saved.file_path)).description == "now described"
        assert _header_id(saved.file_path) == saved.workflow_id
        assert isinstance(refused, SetWorkflowMetadataResultFailure)
        assert "never changes" in str(refused.result_details)
        assert _header_id(saved.file_path) == saved.workflow_id

    def test_move_keeps_the_id(self, project_engine: Engine, workspace: Path) -> None:
        saved = _saved_workflow(project_engine, "mover")

        moved = project_engine.handle_request(
            MoveWorkflowRequest(workflow_name=saved.workflow_name, target_directory="elsewhere")
        )

        assert isinstance(moved, MoveWorkflowResultSuccess), moved.result_details
        assert moved.workflow_id == saved.workflow_id
        assert _header_id(workspace / moved.moved_file_path) == saved.workflow_id

    def test_rename_of_the_open_workflow_keeps_its_id_and_stays_open(self, project_engine: Engine) -> None:
        workflow_id = _open_new_workflow(project_engine, "before")
        saved = _save(project_engine)
        flow_name = project_engine.context_manager.get_current_flow().name

        renamed = _run(project_engine, RenameWorkflowRequest(workflow_name=saved.workflow_name, requested_name="after"))

        assert isinstance(renamed, RenameWorkflowResultSuccess), renamed.result_details
        assert renamed.workflow_id == workflow_id
        assert renamed.new_workflow_name == "after"
        assert not Path(saved.file_path).exists()
        entry = project_engine.workflow_registry.get(workflow_id)
        assert entry.absolute_path is not None
        assert _header_id(entry.absolute_path) == workflow_id
        # Still open, graph and all: renaming does not close the workflow.
        assert project_engine.context_manager.get_current_workflow_id() == workflow_id
        assert project_engine.context_manager.get_current_workflow_name() == "after"
        assert project_engine.context_manager.get_current_flow().name == flow_name

    def test_rename_of_an_open_library_workflow_is_refused(self, project_engine: Engine) -> None:
        library_id = _open_new_workflow(project_engine, "library_workflow")
        library_saved = _save(project_engine)
        project_engine.workflow_registry.get(library_id).metadata.is_griptape_provided = True

        renamed = _run(
            project_engine, RenameWorkflowRequest(workflow_name=library_saved.workflow_name, requested_name="mine")
        )

        assert isinstance(renamed, RenameWorkflowResultFailure)
        assert "a library provides it" in str(renamed.result_details)
        assert Path(library_saved.file_path).is_file()
        assert _header_id(library_saved.file_path) == library_id
        assert project_engine.workflow_registry.get(library_id).absolute_path == Path(library_saved.file_path)
        assert project_engine.workflow_registry.find_by_name("mine") is None
        assert project_engine.context_manager.get_current_workflow_id() == library_id

    def test_renaming_only_the_letter_case_keeps_the_file(self, project_engine: Engine, workspace: Path) -> None:
        """On a case-insensitive filesystem the new name is the same file, which must not be deleted."""
        probe = workspace / "Case_Probe.txt"
        probe.write_text("probe")
        case_insensitive = (workspace / "case_probe.txt").exists()
        probe.unlink()
        if not case_insensitive:
            pytest.skip("the filesystem is case-sensitive, so the new name is a different file")
        workflow_id = _open_new_workflow(project_engine, "Shot")
        saved = _save(project_engine, SaveWorkflowRequest(file_name="Shot"))

        renamed = _run(project_engine, RenameWorkflowRequest(workflow_name=saved.workflow_name, requested_name="shot"))

        assert isinstance(renamed, RenameWorkflowResultSuccess), renamed.result_details
        entry = project_engine.workflow_registry.get(workflow_id)
        assert entry.absolute_path is not None
        assert entry.absolute_path.exists()
        assert _header_id(entry.absolute_path) == workflow_id
        # The file on disk takes the new letter case, so a rescan finds the renamed workflow.
        assert entry.absolute_path.name in [path.name for path in entry.absolute_path.parent.iterdir()]
        _close(project_engine)
        _scan(project_engine, workspace)
        rescanned = project_engine.workflow_registry.find_by_name(renamed.new_workflow_name)
        assert rescanned is not None
        assert rescanned.workflow_id == workflow_id

    def test_save_subflow_keeps_the_parent_id(self, project_engine: Engine) -> None:
        workflow_id = _open_new_workflow(project_engine, "parent")
        saved = _save(project_engine)
        top = project_engine.handle_request(GetTopLevelFlowRequest())
        assert isinstance(top, GetTopLevelFlowResultSuccess)
        subflow = project_engine.handle_request(
            CreateFlowRequest(parent_flow_name=top.flow_name, flow_name="Sub", set_as_new_context=False)
        )
        assert isinstance(subflow, CreateFlowResultSuccess), subflow.result_details

        result = _run(project_engine, SaveSubflowToWorkflowRequest(flow_name="Sub", workflow_name=saved.workflow_name))

        assert isinstance(result, SaveSubflowToWorkflowResultSuccess), result.result_details
        assert result.workflow_metadata.workflow_id == workflow_id
        assert _header_id(saved.file_path) == workflow_id


class TestUnreadableHeaderRefusesBranchRequests:
    @pytest.mark.parametrize(
        ("request_type", "failure_type", "name_field"),
        [
            (CreateWorkflowFromTemplateRequest, CreateWorkflowFromTemplateResultFailure, "template_name"),
            (MergeWorkflowBranchRequest, MergeWorkflowBranchResultFailure, "workflow_name"),
            (ResetWorkflowBranchRequest, ResetWorkflowBranchResultFailure, "workflow_name"),
        ],
    )
    def test_each_fails_without_touching_files(
        self,
        project_engine: Engine,
        workspace: Path,
        request_type: type,
        failure_type: type,
        name_field: str,
    ) -> None:
        workflow_file = workspace / "damaged.py"
        workflow_file.write_text("print('no header')\n", encoding="utf-8")
        opened = read_metadata_for_open_file(workflow_file)
        assert opened.metadata_error is not None
        workflow = project_engine.workflow_registry.register_file(
            workflow_file, opened.metadata, metadata_error=opened.metadata_error
        )
        content = workflow_file.read_text(encoding="utf-8")
        files_before = sorted(workspace.rglob("*"))

        result = project_engine.handle_request(request_type(**{name_field: workflow.name}))

        assert isinstance(result, failure_type)
        assert "could not be read" in str(result.result_details)
        assert workflow_file.read_text(encoding="utf-8") == content
        assert sorted(workspace.rglob("*")) == files_before
        assert project_engine.workflow_registry.get(workflow.workflow_id) is workflow


class TestSaveWorkflowFileFromSerializedFlowStampsAnId:
    """Writing back into a registered workflow's file keeps its id; any other file gets a new one."""

    @staticmethod
    def _written_id(engine: Engine, request: SaveWorkflowFileFromSerializedFlowRequest) -> str:
        with patch.object(engine.workflow_manager.saver, "_save_workflow_file_inline") as save_inline:
            asyncio.run(engine.workflow_manager.saver.on_save_workflow_file_from_serialized_flow_request(request))
        return save_inline.call_args.kwargs["workflow_id"]

    def test_a_registered_file_keeps_its_workflows_id(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        workflow_file = _write_workflow_file(workspace / "lineage.py", workflow_id=LINEAGE_ID)
        engine.workflow_registry.register_file(workflow_file, read_workflow_metadata(workflow_file))

        written_id = self._written_id(
            engine,
            SaveWorkflowFileFromSerializedFlowRequest(
                serialized_flow_commands=MagicMock(), file_name="lineage", file_path=str(workflow_file)
            ),
        )

        assert written_id == LINEAGE_ID

    def test_any_other_file_gets_a_new_id(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        engine.workflow_registry.register_file(
            _write_workflow_file(workspace / "lineage.py", workflow_id=LINEAGE_ID),
            read_workflow_metadata(workspace / "lineage.py"),
        )

        to_new_path = self._written_id(
            engine,
            SaveWorkflowFileFromSerializedFlowRequest(
                serialized_flow_commands=MagicMock(), file_name="packaged", file_path=str(workspace / "packaged.py")
            ),
        )
        to_situation = self._written_id(
            engine, SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=MagicMock(), file_name="named")
        )

        assert to_new_path not in (None, LINEAGE_ID)
        assert to_situation not in (None, LINEAGE_ID, to_new_path)


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

    def test_the_derived_id_is_written_on_the_next_save(self, project_engine: Engine, workspace: Path) -> None:
        workflow_file = _write_workflow_file(workspace / "legacy.py", workflow_id=None, name="legacy")
        _scan(project_engine, workspace)
        entry = project_engine.workflow_registry.find_by_path(workflow_file)
        assert entry is not None
        project_engine.context_manager.push_workflow(workflow_id=entry.workflow_id)
        created = project_engine.handle_request(CreateFlowRequest(parent_flow_name=None, set_as_new_context=True))
        assert isinstance(created, CreateFlowResultSuccess), created.result_details

        saved = _save(project_engine, SaveWorkflowRequest(file_name=entry.name))

        assert saved.workflow_id == entry.workflow_id
        assert _header_id(workflow_file) == entry.workflow_id

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

    def test_the_open_workflow_keeps_its_id(self, workspace: Path) -> None:
        engine = current_engine()
        engine.config_manager.workspace_path = workspace
        opened = _write_workflow_file(workspace / "z_opened.py", workflow_id=SHARED_ID)
        _scan(engine, workspace)
        engine.context_manager.push_workflow(file_path=str(opened))
        copy = workspace / "a_copy.py"
        shutil.copy(opened, copy)

        with patch("griptape_nodes.retained_mode.managers.workflow.identity.file_birth_time", return_value=None):
            _scan(engine, workspace)

        assert engine.context_manager.get_current_workflow_id() == SHARED_ID
        assert _header_id(opened) == SHARED_ID
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


class TestIdsOnResults:
    def test_context_and_heartbeat_report_the_id(self) -> None:
        engine = current_engine()
        workflow_id = _open_new_workflow(engine, "reported")

        context = engine.handle_request(GetWorkflowContextRequest())
        heartbeat = engine.handle_request(EngineHeartbeatRequest(heartbeat_id="beat"))

        assert isinstance(context, GetWorkflowContextSuccess)
        assert context.workflow_id == workflow_id
        assert isinstance(heartbeat, EngineHeartbeatResultSuccess)
        assert heartbeat.current_workflow_id == workflow_id


class TestIdentityAcrossTheWorkflowLifecycle:
    """One workflow keeps one id through create, save, rename, move, reopen, restart and refresh."""

    def test_the_id_never_changes(self, workspace: Path) -> None:
        engine = current_engine()
        _use_default_project(engine, workspace)
        workflow_id = _open_new_workflow(engine, "lifecycle")

        saved = _save(engine)
        assert saved.workflow_id == workflow_id

        renamed = _run(engine, RenameWorkflowRequest(workflow_name=saved.workflow_name, requested_name="renamed"))
        assert isinstance(renamed, RenameWorkflowResultSuccess), renamed.result_details
        assert renamed.workflow_id == workflow_id
        _close(engine)

        moved = engine.handle_request(MoveWorkflowRequest(workflow_name="renamed", target_directory="shots"))
        assert isinstance(moved, MoveWorkflowResultSuccess), moved.result_details
        assert moved.workflow_id == workflow_id

        reopened = _run(engine, RunWorkflowFromRegistryRequest(workflow_name=moved.new_workflow_name))
        assert isinstance(reopened, RunWorkflowFromRegistryResultSuccess), reopened.result_details
        assert reopened.workflow_id == workflow_id
        assert engine.context_manager.get_current_workflow_id() == workflow_id
        _close(engine)
        engine.handle_request(SetCurrentProjectRequest(project_id=None))

        # Restart: a new engine finds the workflow by scanning, and reads the id from its header.
        reset_root_engine()
        restarted = current_engine()
        _use_default_project(restarted, workspace)
        _scan(restarted, workspace)
        found = restarted.workflow_registry.get(workflow_id)
        assert found.name == "shots/renamed"

        _scan(restarted, workspace)
        assert restarted.workflow_registry.get(workflow_id).name == "shots/renamed"
        restarted.handle_request(SetCurrentProjectRequest(project_id=None))
