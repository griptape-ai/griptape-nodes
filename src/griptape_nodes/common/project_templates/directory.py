"""Directory definition for logical project directories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.loader import YAMLLineInfo
    from griptape_nodes.common.project_templates.validation import ProjectValidationInfo


@dataclass
class DirectoryDefinition:
    """Definition of a logical directory in the project."""

    name: str  # Logical name (e.g., "inputs", "outputs")
    path_schema: str  # Path string (may contain macros/env vars)

    @staticmethod
    def from_dict(
        data: dict[str, Any],
        field_path: str,
        validation_info: ProjectValidationInfo,
        line_info: YAMLLineInfo,
    ) -> DirectoryDefinition:
        """Construct from YAML dict, validating and populating validation_info.

        Validates:
        - path_schema is a string
        - Basic syntax checks (no invalid characters, etc.)

        Note: Macro resolution validation happens later in ProjectManager.
        """
        # Extract name (should be provided by caller from dict key)
        name = data.get("name", "unknown")

        # Extract path_schema
        path_schema = data.get("path_schema")
        if path_schema is None:
            validation_info.add_error(
                field_path=f"{field_path}.path_schema",
                message="Missing required field 'path_schema'",
                line_number=line_info.get_line(field_path),
            )
            path_schema = ""  # Fallback
        elif not isinstance(path_schema, str):
            validation_info.add_error(
                field_path=f"{field_path}.path_schema",
                message=f"Field 'path_schema' must be string, got {type(path_schema).__name__}",
                line_number=line_info.get_line(f"{field_path}.path_schema"),
            )
            path_schema = ""  # Fallback

        return DirectoryDefinition(name=name, path_schema=path_schema)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary suitable for YAML export."""
        return {
            "path_schema": self.path_schema,
        }

    @staticmethod
    def merge(
        base: DirectoryDefinition,
        overlay_data: dict[str, Any],
        field_path: str,
        validation_info: ProjectValidationInfo,
        line_info: YAMLLineInfo,
    ) -> DirectoryDefinition:
        """Merge overlay fields onto base directory.

        Field-level merge behavior:
        - path_schema: Use overlay if present, else base

        Args:
            base: Complete base directory
            overlay_data: Partial directory dict from overlay
            field_path: Path for validation errors (e.g., "directories.inputs")
            validation_info: Shared validation info
            line_info: Line tracking from overlay

        Returns:
            New merged DirectoryDefinition (constructed via from_dict)
        """
        # Start with base fields
        merged_data = {"name": base.name, "path_schema": base.path_schema}

        # Apply overlay if present
        if "path_schema" in overlay_data:
            merged_data["path_schema"] = overlay_data["path_schema"]

        return DirectoryDefinition.from_dict(
            data=merged_data,
            field_path=field_path,
            validation_info=validation_info,
            line_info=line_info,
        )
