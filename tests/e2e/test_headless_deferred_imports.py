"""Regression test for issue #4738: library-derived imports must be inside build_workflow().

When a workflow parameter value holds a class from a dynamically-loaded library module
(e.g. DiffusionPipelineArtifact from modular_diffusion_nodes_library), the generator
used to emit `from <library_module> import <Class>` at module top level. In headless mode
this causes a ModuleNotFoundError because the import runs before build_workflow() calls
RegisterLibraryFromFileRequest, which is what adds the library to sys.path.

This test verifies that after the fix, such imports appear inside build_workflow() (after
the RegisterLibraryFromFileRequest calls) rather than at module top level.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from griptape_nodes.node_library.workflow_registry import WorkflowMetadata
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    CreateFlowResultSuccess,
    SerializeFlowToCommandsRequest,
    SerializeFlowToCommandsResultSuccess,
)
from griptape_nodes.retained_mode.events.library_events import (
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromFileResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, CreateNodeResultSuccess
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

FIXTURE_LIBRARY_DIR = Path(__file__).parent / "fixtures" / "artifact_library"
FIXTURE_LIBRARY_JSON_TEMPLATE = FIXTURE_LIBRARY_DIR / "griptape_nodes_library.json"


def _materialize_library(target_dir: Path) -> Path:
    from griptape_nodes.utils.version_utils import engine_version

    target_dir.mkdir(parents=True, exist_ok=True)
    schema = json.loads(FIXTURE_LIBRARY_JSON_TEMPLATE.read_text())
    schema["metadata"]["engine_version"] = engine_version
    library_json = target_dir / "griptape_nodes_library.json"
    library_json.write_text(json.dumps(schema, indent=2))
    node_file = FIXTURE_LIBRARY_DIR / "artifact_node.py"
    (target_dir / node_file.name).write_text(node_file.read_text())
    return library_json


def _find_build_workflow_body(tree: ast.Module) -> list[ast.stmt]:
    """Return the body of async def build_workflow() from a parsed workflow module."""
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "build_workflow":
            return node.body
    msg = "build_workflow() not found in generated source"
    raise AssertionError(msg)


def _import_from_names(stmts: list[ast.stmt]) -> list[tuple[str, list[str]]]:
    """Return (module, [names]) for every ImportFrom in stmts."""
    return [
        (node.module or "", [alias.name for alias in node.names]) for node in stmts if isinstance(node, ast.ImportFrom)
    ]


@pytest.mark.skipif(
    not FIXTURE_LIBRARY_JSON_TEMPLATE.exists(),
    reason=f"Artifact Library fixture missing at {FIXTURE_LIBRARY_JSON_TEMPLATE}",
)
def test_library_artifact_import_is_inside_build_workflow(tmp_path: Path) -> None:
    """Library-derived imports must appear inside build_workflow(), not at module top.

    Regression for #4738: previously `from <library_module> import FakeArtifact` was
    emitted at module top, causing ModuleNotFoundError in headless execution because
    the import ran before RegisterLibraryFromFileRequest set up sys.path.
    """
    GriptapeNodes.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))

    library_json = _materialize_library(tmp_path / "library")

    register_result = GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path=str(library_json)))
    assert isinstance(register_result, RegisterLibraryFromFileResultSuccess), register_result

    GriptapeNodes.ContextManager().push_workflow(workflow_name="artifact_test_workflow")

    flow_result = GriptapeNodes.handle_request(
        CreateFlowRequest(parent_flow_name=None, flow_name="ControlFlow_1", set_as_new_context=False)
    )
    assert isinstance(flow_result, CreateFlowResultSuccess), flow_result

    node_result = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="ArtifactNode",
            specific_library_name="Artifact Library",
            node_name="Artifact_1",
            override_parent_flow_name=flow_result.flow_name,
        )
    )
    assert isinstance(node_result, CreateNodeResultSuccess), node_result
    assert node_result.node_type == "ArtifactNode", f"Expected ArtifactNode, got {node_result.node_type!r}"

    # Run the node so its FakeArtifact output gets populated — the serializer only
    # pickles non-None values, so we need process() to have run first.
    node = GriptapeNodes.NodeManager().get_node_by_name("Artifact_1")
    node.process()

    serialize_result = GriptapeNodes.handle_request(SerializeFlowToCommandsRequest(flow_name=flow_result.flow_name))
    assert isinstance(serialize_result, SerializeFlowToCommandsResultSuccess), serialize_result

    metadata = WorkflowMetadata(
        name="artifact_test_workflow",
        schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
        engine_version_created_with="0.0.0",
        node_libraries_referenced=list(serialize_result.serialized_flow_commands.node_dependencies.libraries),
        workflow_shape=None,
    )
    source = GriptapeNodes.WorkflowManager()._generate_workflow_file_content(
        serialized_flow_commands=serialize_result.serialized_flow_commands,
        workflow_metadata=metadata,
    )

    tree = ast.parse(source)

    # Must NOT appear at module top level
    library_imports_at_top = [(mod, names) for mod, names in _import_from_names(tree.body) if "artifact_node" in mod]
    assert not library_imports_at_top, (
        f"Library-derived import found at module top level (issue #4738 regression): {library_imports_at_top}\n"
        "It must be inside build_workflow() instead."
    )

    # Must appear inside build_workflow()
    build_workflow_body = _find_build_workflow_body(tree)
    library_imports_in_func = [
        (mod, names) for mod, names in _import_from_names(build_workflow_body) if "artifact_node" in mod
    ]
    assert library_imports_in_func, (
        f"FakeArtifact import not found inside build_workflow().\nGenerated source:\n{source}"
    )

    # Must come after all RegisterLibraryFromFileRequest calls
    register_indices = [
        i
        for i, stmt in enumerate(build_workflow_body)
        if isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Await)
        and "RegisterLibraryFromFileRequest" in ast.unparse(stmt)
    ]
    import_indices = [
        i
        for i, stmt in enumerate(build_workflow_body)
        if isinstance(stmt, ast.ImportFrom) and "artifact_node" in (stmt.module or "")
    ]
    assert register_indices
    assert import_indices
    assert min(import_indices) > max(register_indices), (
        "Deferred library import must appear AFTER all RegisterLibraryFromFileRequest calls in build_workflow()"
    )
