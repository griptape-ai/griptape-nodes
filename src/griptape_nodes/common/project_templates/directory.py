"""Directory definition for logical project directories."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, ValidationError, model_validator

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.loader import YAMLLineInfo
    from griptape_nodes.common.project_templates.validation import ProjectValidationInfo


class PerPlatformPathMacro(BaseModel):
    """Per-platform path macro mapping for directory definitions.

    At least one of `linux`, `darwin`, `windows`, or `default` must be set.
    `default` is consulted when the active platform's key is absent. Field
    names mirror the `Platform` StrEnum values used elsewhere in the engine.
    """

    linux: str | None = Field(default=None, description="Path macro used on Linux")
    darwin: str | None = Field(default=None, description="Path macro used on macOS")
    windows: str | None = Field(default=None, description="Path macro used on Windows")
    default: str | None = Field(default=None, description="Fallback path macro when the active platform's key is unset")

    @model_validator(mode="after")
    def _at_least_one_key(self) -> PerPlatformPathMacro:
        if self.linux is None and self.darwin is None and self.windows is None and self.default is None:
            msg = "PerPlatformPathMacro requires at least one of 'linux', 'darwin', 'windows', or 'default'"
            raise ValueError(msg)
        return self

    def select(self) -> str | None:
        """Return the path macro for the active platform, falling back to `default`."""
        active = _active_platform_key()
        if active == "linux" and self.linux is not None:
            return self.linux
        if active == "darwin" and self.darwin is not None:
            return self.darwin
        if active == "windows" and self.windows is not None:
            return self.windows
        return self.default


def _active_platform_key() -> str:
    """Map sys.platform to one of the PerPlatformPathMacro keys."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("darwin"):
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    return ""


class DirectoryDefinition(BaseModel):
    """Definition of a logical directory in the project."""

    name: str = Field(description="Logical name (e.g., 'inputs', 'outputs')")
    path_macro: str | PerPlatformPathMacro = Field(
        description="Path string (may contain macros/env vars), or a per-platform mapping"
    )

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
        - path_macro: Use overlay if present, else base. Atomic — when overlay supplies the
          per-platform mapping form, it fully replaces the base value (no per-key deep merge).

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
        merged_data: dict[str, Any] = {"name": base.name, "path_macro": base.path_macro}

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
