"""Directory definition for logical project directories."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.loader import YAMLLineInfo
    from griptape_nodes.common.project_templates.validation import ProjectValidationInfo


class DirectoryDefinition(BaseModel):
    """Definition of a logical directory in the project."""

    name: str = Field(description="Logical name (e.g., 'inputs', 'outputs')")
    path_macro: str = Field(description="Path string (may contain macros/env vars)")

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
        - path_macro: Use overlay if present, else base

        Args:
            base: Complete base directory
            overlay_data: Partial directory dict from overlay
            field_path: Path for validation errors (e.g., "directories.inputs")
            validation_info: Shared validation info
            line_info: Line tracking from overlay

        Returns:
            New merged DirectoryDefinition
        """
        # Start with base fields
        merged_data = {"name": base.name, "path_macro": base.path_macro}

        # Apply overlay if present
        if "path_macro" in overlay_data:
            merged_data["path_macro"] = overlay_data["path_macro"]

        try:
            return DirectoryDefinition.model_validate(merged_data)
        except ValidationError as e:
            # Convert Pydantic validation errors to our validation_info format
            for error in e.errors():
                error_field_path = ".".join(str(loc) for loc in error["loc"])
                full_field_path = f"{field_path}.{error_field_path}"
                message = error["msg"]
                line_number = line_info.get_line(full_field_path)

                validation_info.add_error(
                    field_path=full_field_path,
                    message=message,
                    line_number=line_number,
                )

            # Return base on validation error (fault-tolerant)
            return base
