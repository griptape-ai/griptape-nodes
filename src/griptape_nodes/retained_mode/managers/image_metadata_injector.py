"""Automatic workflow metadata injection for PNG images saved through StaticFilesManager.

This module provides functionality to automatically inject workflow metadata into
PNG images when they are saved. Metadata is stored in PNG text chunks.
"""

import logging
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, PngImagePlugin

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.type_validator import TypeValidator

logger = logging.getLogger("griptape_nodes")

# Metadata namespace prefix for all auto-injected fields
METADATA_NAMESPACE = "gtn_"

# Supported image formats mapped by file extension
SUPPORTED_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".tiff": "TIFF",
    ".tif": "TIFF",
    ".mpo": "MPO",
}


def get_image_format_from_filename(filename: str) -> str | None:
    """Extract image format from filename extension.

    Args:
        filename: Name of the file including extension

    Returns:
        Image format string (e.g., "JPEG", "PNG") or None if not a supported image format
    """
    ext = Path(filename).suffix.lower()
    return SUPPORTED_FORMATS.get(ext)


def supports_metadata(format_str: str | None) -> bool:
    """Check if image format supports metadata injection (PNG only).

    Args:
        format_str: Image format string (e.g., "PNG")

    Returns:
        True if format is PNG
    """
    if format_str is None:
        return False
    return format_str.upper() == "PNG"


def _serialize_node(node_name: str) -> str | None:
    """Serialize a specific node to JSON commands.

    Args:
        node_name: Name of the node to serialize

    Returns:
        JSON string of serialized node commands, or None if serialization fails
    """
    from griptape_nodes.retained_mode.events.node_events import (
        SerializeNodeToCommandsRequest,
        SerializeNodeToCommandsResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    serialize_request = SerializeNodeToCommandsRequest(
        node_name=node_name,
        serialize_all_parameter_values=True,
    )
    serialize_result = GriptapeNodes.handle_request(serialize_request)

    if isinstance(serialize_result, SerializeNodeToCommandsResultSuccess):
        # Convert to dict and then to JSON string
        return serialize_result.to_json()

    return None


def _collect_parameter_values(node_name: str) -> dict[str, Any] | None:
    """Collect current parameter values from a node's INPUT and PROPERTY parameters.

    Args:
        node_name: Name of the node to collect parameters from

    Returns:
        Dictionary of parameter names to serialized values, or None if collection fails
    """
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    # Failure case: Attempt to get node object
    obj_mgr = GriptapeNodes.ObjectManager()
    try:
        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
    except Exception as e:
        logger.warning("Failed to get node '%s' for parameter collection: %s", node_name, e)
        return None

    if node is None:
        logger.warning("Node '%s' not found for parameter collection", node_name)
        return None

    # Get all parameters from node
    all_parameters = node.parameters

    # Filter to INPUT and PROPERTY mode parameters only
    eligible_parameters = [
        param
        for param in all_parameters
        if ParameterMode.INPUT in param.allowed_modes or ParameterMode.PROPERTY in param.allowed_modes
    ]

    # Collect and serialize parameter values
    parameter_values = {}

    for param in eligible_parameters:
        # Get current value
        value = node.get_parameter_value(param.name)

        # Skip None values (not set)
        if value is None:
            continue

        # Serialize value with error handling
        try:
            serialized_value = TypeValidator.safe_serialize(value)
            parameter_values[param.name] = serialized_value
        except Exception as e:
            logger.warning("Failed to serialize parameter '%s' on node '%s': %s", param.name, node_name, e)
            continue

    # Success path: return collected values (may be empty dict)
    return parameter_values


def _collect_workflow_details(workflow_name: str, metadata: dict[str, str]) -> None:
    """Collect workflow details from registry and add to metadata dict.

    Args:
        workflow_name: Name of the workflow
        metadata: Dictionary to populate with workflow metadata (modified in-place)
    """
    from griptape_nodes.node_library.workflow_registry import WorkflowRegistry

    try:
        workflow = WorkflowRegistry.get_workflow_by_name(workflow_name)

        if workflow.metadata.creation_date:
            metadata[f"{METADATA_NAMESPACE}workflow_created"] = workflow.metadata.creation_date.isoformat()

        if workflow.metadata.last_modified_date:
            metadata[f"{METADATA_NAMESPACE}workflow_modified"] = workflow.metadata.last_modified_date.isoformat()

        if workflow.metadata.engine_version_created_with:
            metadata[f"{METADATA_NAMESPACE}engine_version"] = workflow.metadata.engine_version_created_with

        if workflow.metadata.description:
            metadata[f"{METADATA_NAMESPACE}workflow_description"] = workflow.metadata.description
    except Exception:  # noqa: S110
        pass


def collect_workflow_metadata() -> dict[str, str]:
    """Collect available workflow metadata from current execution context.

    Gathers metadata from GriptapeNodes ContextManager and WorkflowRegistry.
    All keys are prefixed with METADATA_NAMESPACE to avoid conflicts.

    Returns:
        Dictionary of metadata key-value pairs, may be empty if no context available
    """
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    metadata = {}

    # Add save timestamp (always available)
    metadata[f"{METADATA_NAMESPACE}saved_at"] = datetime.now(UTC).isoformat()

    # Get context manager
    context_manager = GriptapeNodes.ContextManager()

    # Check workflow context
    if not context_manager.has_current_workflow():
        return metadata

    # Get workflow name
    try:
        workflow_name = context_manager.get_current_workflow_name()
        metadata[f"{METADATA_NAMESPACE}workflow_name"] = workflow_name
        _collect_workflow_details(workflow_name, metadata)
    except Exception:  # noqa: S110
        pass

    # Get flow context and resolving nodes
    if context_manager.has_current_flow():
        try:
            flow = context_manager.get_current_flow()
            metadata[f"{METADATA_NAMESPACE}flow_name"] = flow.name

            # Get resolving nodes (currently running nodes) from flow_state
            flow_manager = GriptapeNodes.FlowManager()
            _, resolving_nodes, _ = flow_manager.flow_state(flow)

            if resolving_nodes:
                # Store node name(s) - if multiple, join with comma
                metadata[f"{METADATA_NAMESPACE}node_name"] = ", ".join(resolving_nodes)

                # Serialize the first resolving node to commands
                # (Multiple nodes rarely run simultaneously during save operations)
                node_commands = _serialize_node(resolving_nodes[0])
                if node_commands:
                    metadata[f"{METADATA_NAMESPACE}node_commands"] = node_commands

                # Collect parameter values from the first resolving node
                parameter_values = _collect_parameter_values(resolving_nodes[0])
                if parameter_values:
                    # Store each parameter as its own metadata key
                    for param_name, param_value in parameter_values.items():
                        metadata[f"{METADATA_NAMESPACE}param_{param_name}"] = str(param_value)
        except Exception:
            logger.exception("Failed to collect flow/node metadata")

    return metadata


def inject_workflow_metadata_if_image(data: bytes, file_name: str) -> bytes:  # noqa: PLR0911
    """Inject workflow metadata into image if format supports it.

    Main entry point for automatic metadata injection. Detects image format,
    collects workflow metadata, and injects into appropriate format (EXIF or PNG).

    Args:
        data: Raw image bytes
        file_name: Filename including extension

    Returns:
        Image bytes with metadata injected, or original bytes if:
        - Format doesn't support metadata
        - No workflow context available
        - Image loading/processing fails
    """
    # Validation: Check format
    format_str = get_image_format_from_filename(file_name)
    if not supports_metadata(format_str):
        return data

    # Validation: Check if we have data
    if not data:
        logger.warning("Cannot inject metadata: empty data")
        return data

    # Collect metadata
    metadata = collect_workflow_metadata()
    if not metadata:
        # No context available, nothing to inject
        return data

    # Load PIL image
    try:
        pil_image = Image.open(BytesIO(data))
    except Exception as e:
        logger.warning("Failed to load image for metadata injection: %s", e)
        return data

    # Verify format matches
    if pil_image.format is None:
        logger.warning("Could not detect image format from data")
        return data

    # Inject metadata (PNG only)
    if pil_image.format != "PNG":
        # Only PNG format supported for workflow metadata
        return data

    try:
        return _inject_png_metadata(pil_image, metadata)
    except Exception as e:
        logger.warning("Failed to inject metadata into %s: %s", file_name, e)
        return data


def _inject_png_metadata(pil_image: Image.Image, metadata: dict[str, str]) -> bytes:
    """Inject metadata into PNG text chunks.

    Creates PngInfo with existing text chunks and adds new metadata.

    Args:
        pil_image: PIL Image to inject metadata into
        metadata: Dictionary of key-value pairs to inject

    Returns:
        Image bytes with metadata injected

    Raises:
        Exception: On PNG save errors
    """
    # Create PNG info with existing metadata
    png_info = PngImagePlugin.PngInfo()

    # Preserve existing text chunks (PIL unpacks them into pil_image.info directly)
    for key, value in pil_image.info.items():
        # Only preserve string key-value pairs (text chunks), skip binary data
        if isinstance(key, str) and isinstance(value, str) and key not in metadata:
            png_info.add_text(key, value)

    # Add new metadata (workflow metadata overwrites duplicates)
    for key, value in metadata.items():
        png_info.add_text(key, str(value))

    # Save with metadata
    output_buffer = BytesIO()
    pil_image.save(output_buffer, format="PNG", pnginfo=png_info)
    return output_buffer.getvalue()
