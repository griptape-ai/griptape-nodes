"""Sidecar metadata file creation for files written through the retained mode API.

When a file is saved, a sidecar JSON file is written alongside it in a `.gtn/`
subdirectory. The sidecar captures caller-provided project context (situation name,
macro template, variable values) merged with auto-collected workflow metadata
(workflow name, flow context, node parameters).

Example layout:
    outputs/
      image.png
      .gtn/
        image.png.json
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from griptape_nodes.retained_mode.managers.artifact_providers.image.metadata import collect_workflow_metadata

if TYPE_CHECKING:
    from pathlib import Path

    from griptape_nodes.common.project_templates.situation import SituationTemplate

logger = logging.getLogger("griptape_nodes")

SIDECAR_DIR = ".gtn"
SCHEMA_VERSION = "0.1.0"

# Keys from collect_workflow_metadata that are dropped from sidecars (too large / internal)
_OMIT_FROM_SIDECAR = {"gtn_flow_commands"}


class SituationPolicy(BaseModel):
    """File collision and directory creation policy from the situation template."""

    on_collision: str | None = None
    create_dirs: bool | None = None


class SituationMetadata(BaseModel):
    """Situation context captured at save time."""

    name: str | None = None
    macro: str | None = None
    policy: SituationPolicy | None = None


class WorkflowMetadata(BaseModel):
    """Workflow-level metadata captured at save time."""

    name: str | None = None
    created: str | None = None
    modified: str | None = None
    engine_version: str | None = None
    description: str | None = None


class FlowMetadata(BaseModel):
    """Flow and node context captured at save time."""

    name: str | None = None
    node_name: str | None = None


class SidecarContent(BaseModel):
    """Root model for the sidecar JSON file written alongside saved files."""

    schema_version: str
    saved_at: str
    situation: SituationMetadata | None = None
    variables: dict[str, str] | None = None
    workflow: WorkflowMetadata | None = None
    flow: FlowMetadata | None = None
    parameters: dict[str, str] | None = None


def get_sidecar_path(file_path: Path) -> Path:
    """Return the sidecar path for a given file.

    Args:
        file_path: Absolute path to the saved file.

    Returns:
        Path to the sidecar JSON file inside the `.gtn/` subdirectory.
    """
    return file_path.parent / SIDECAR_DIR / (file_path.name + ".json")


def build_situation_metadata(
    situation_name: str,
    situation: SituationTemplate,
    variables: dict[str, Any],
) -> dict[str, str]:
    """Build a flat metadata dict from situation context.

    Args:
        situation_name: Name of the situation (e.g., "save_node_output").
        situation: The resolved SituationTemplate.
        variables: Macro variable values used when resolving the situation.

    Returns:
        Flat dict with "gtn_"-prefixed keys ready to pass as WriteFileRequest.file_metadata.
    """
    metadata: dict[str, str] = {
        "gtn_situation_name": situation_name,
        "gtn_situation_macro": situation.macro,
        "gtn_situation_policy_on_collision": str(situation.policy.on_collision),
        "gtn_situation_policy_create_dirs": "true" if situation.policy.create_dirs else "false",
    }
    for key, value in variables.items():
        metadata[f"gtn_variable_{key}"] = str(value)
    return metadata


def _extract_situation_block(merged: dict[str, str]) -> SituationMetadata | None:
    """Extract and remove situation keys from merged dict, returning a nested block."""
    if "gtn_situation_name" in merged:
        name = merged.pop("gtn_situation_name")
        macro = merged.pop("gtn_situation_macro", None)
        on_collision = merged.pop("gtn_situation_policy_on_collision", None)
        create_dirs_str = merged.pop("gtn_situation_policy_create_dirs", None)
        policy = None
        if on_collision is not None or create_dirs_str is not None:
            create_dirs = (create_dirs_str == "true") if create_dirs_str is not None else None
            policy = SituationPolicy(on_collision=on_collision, create_dirs=create_dirs)
        return SituationMetadata(name=name, macro=macro, policy=policy)
    if "gtn_macro_template" in merged:
        # MacroPath-only callers (no situation) still capture the macro template
        return SituationMetadata(macro=merged.pop("gtn_macro_template"))
    return None


def _extract_prefixed_block(merged: dict[str, str], prefix: str) -> dict[str, str]:
    """Extract and remove all keys with the given prefix, stripping the prefix from returned keys."""
    result: dict[str, str] = {}
    for key in list(merged.keys()):
        if key.startswith(prefix):
            result[key[len(prefix) :]] = merged.pop(key)
    return result


def _extract_workflow_block(merged: dict[str, str]) -> WorkflowMetadata | None:
    """Extract and remove workflow keys from merged dict, returning a nested block."""
    fields: dict[str, str] = {}
    for src_key, dst_key in [
        ("gtn_workflow_name", "name"),
        ("gtn_workflow_created", "created"),
        ("gtn_workflow_modified", "modified"),
        ("gtn_engine_version", "engine_version"),
        ("gtn_workflow_description", "description"),
    ]:
        if src_key in merged:
            fields[dst_key] = merged.pop(src_key)
    if not fields:
        return None
    return WorkflowMetadata(**fields)


def _extract_flow_block(merged: dict[str, str]) -> FlowMetadata | None:
    """Extract and remove flow keys from merged dict, returning a nested block."""
    fields: dict[str, str] = {}
    for src_key, dst_key in [
        ("gtn_flow_name", "name"),
        ("gtn_node_name", "node_name"),
    ]:
        if src_key in merged:
            fields[dst_key] = merged.pop(src_key)
    if not fields:
        return None
    return FlowMetadata(**fields)


def build_sidecar_content(file_metadata: dict[str, str] | None) -> SidecarContent:
    """Build the sidecar content by merging file_metadata with workflow context.

    Args:
        file_metadata: Caller-provided metadata (situation, variables, etc.) with "gtn_" keys.
                       May be None if no caller context is available.

    Returns:
        SidecarContent suitable for JSON serialization.
    """
    merged: dict[str, str] = collect_workflow_metadata()
    if file_metadata:
        merged.update(file_metadata)

    for key in _OMIT_FROM_SIDECAR:
        merged.pop(key, None)

    saved_at = merged.pop("gtn_saved_at", "")
    situation = _extract_situation_block(merged)
    variables = _extract_prefixed_block(merged, "gtn_variable_")
    workflow = _extract_workflow_block(merged)
    flow = _extract_flow_block(merged)
    parameters = _extract_prefixed_block(merged, "gtn_param_")

    return SidecarContent(
        schema_version=SCHEMA_VERSION,
        saved_at=saved_at,
        situation=situation,
        variables=variables or None,
        workflow=workflow,
        flow=flow,
        parameters=parameters or None,
    )


def write_sidecar(file_path: Path, file_metadata: dict[str, str] | None) -> None:
    """Write a sidecar JSON metadata file alongside the saved file.

    Creates a `.gtn/<filename>.json` file next to `file_path`. Best-effort:
    failures are logged as warnings and never propagated to callers.

    Args:
        file_path: Absolute path to the file that was just saved.
        file_metadata: Caller-provided context dict (may be None).
    """
    try:
        sidecar_path = get_sidecar_path(file_path)
        content = build_sidecar_content(file_metadata)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(content.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write sidecar metadata for '%s': %s", file_path, e)
