"""Project template main class."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, Field, ValidationError
from ruamel.yaml import YAML

from griptape_nodes.common.project_templates.directory import DirectoryDefinition
from griptape_nodes.common.project_templates.situation import SituationTemplate
from griptape_nodes.common.project_templates.validation import (
    ProjectOverrideAction,
    ProjectOverrideCategory,
    ProjectValidationInfo,
)

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.loader import ProjectOverlayData


class ProjectTemplate(BaseModel):
    """Complete project template loaded from project.yml."""

    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.1.0"

    project_template_schema_version: str = Field(description="Schema version for the project template")
    name: str = Field(description="Name of the project")
    situations: dict[str, SituationTemplate] = Field(description="Situation templates (situation_name -> template)")
    directories: dict[str, DirectoryDefinition] = Field(
        description="Directory definitions (logical_name -> definition)",
    )
    environment: dict[str, str] = Field(default_factory=dict, description="Custom environment variables")
    description: str | None = Field(default=None, description="Description of the project")

    def get_situation(self, situation_name: str) -> SituationTemplate | None:
        """Get a situation by name, returns None if not found."""
        return self.situations.get(situation_name)

    def get_directory(self, directory_name: str) -> DirectoryDefinition | None:
        """Get a directory definition by logical name."""
        return self.directories.get(directory_name)

    def to_yaml(self, *, include_comments: bool = True) -> str:
        """Export project template to YAML string.

        If include_comments=True, adds helpful comments explaining each section.
        """
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False

        data = self.model_dump(mode="json", exclude_none=True)

        # Convert to YAML string
        stream = io.StringIO()
        yaml.dump(data, stream)
        yaml_text = stream.getvalue()

        if include_comments:
            # Add helpful header comment
            header = (
                "# Project Template\n"
                f"# Version: {self.project_template_schema_version}\n"
                "#\n"
                "# This file defines how files are organized and saved in your project.\n"
                "# See documentation for details on customizing situations and directories.\n\n"
            )
            yaml_text = header + yaml_text

        return yaml_text

    @staticmethod
    def merge(  # noqa: C901, PLR0912
        base: ProjectTemplate,
        overlay: ProjectOverlayData,
        validation_info: ProjectValidationInfo,
    ) -> ProjectTemplate:
        """Merge overlay data on top of base template.

        Merge behavior:
        - name: From overlay (required)
        - description: From overlay if present, else base
        - project_template_schema_version: From overlay (required)
        - situations: Dict merge with field-level merging for conflicts
        - directories: Dict merge with field-level merging for conflicts
        - environment: Dict merge (overlay values override base)

        Override tracking (non-status-affecting):
        - Metadata: name (always MODIFIED), description (if different)
        - Situations: MODIFIED if exists in base, ADDED if new
        - Directories: MODIFIED if exists in base, ADDED if new
        - Environment: MODIFIED if exists in base, ADDED if new

        Note: Schema version compatibility should be checked by caller (ProjectManager)
        before calling merge. This method does not validate version compatibility.

        Args:
            base: Fully constructed base template (e.g., system defaults)
            overlay: Partially validated overlay data with raw dicts
            validation_info: Fresh ProjectValidationInfo for tracking overrides and errors

        Returns:
            New fully constructed merged ProjectTemplate with validation_info
        """
        # Track metadata overrides
        validation_info.add_override(
            category=ProjectOverrideCategory.METADATA,
            name="name",
            action=ProjectOverrideAction.MODIFIED,
        )

        if overlay.description is not None and overlay.description != base.description:
            validation_info.add_override(
                category=ProjectOverrideCategory.METADATA,
                name="description",
                action=ProjectOverrideAction.MODIFIED,
            )

        # Merge situations
        merged_situations: dict[str, SituationTemplate] = {}

        # Start with all base situations
        for sit_name, base_sit in base.situations.items():
            if sit_name in overlay.situations:
                # Field-level merge
                merged_sit = SituationTemplate.merge(
                    base=base_sit,
                    overlay_data=overlay.situations[sit_name],
                    field_path=f"situations.{sit_name}",
                    validation_info=validation_info,
                    line_info=overlay.line_info,
                )
                merged_situations[sit_name] = merged_sit

                validation_info.add_override(
                    category=ProjectOverrideCategory.SITUATION,
                    name=sit_name,
                    action=ProjectOverrideAction.MODIFIED,
                )
            else:
                # Inherit from base
                merged_situations[sit_name] = base_sit

        # Add new situations from overlay
        for sit_name, sit_data in overlay.situations.items():
            if sit_name not in base.situations:
                # New situation - construct from scratch
                # Add name to dict for model_validate
                sit_data_with_name = {"name": sit_name, **sit_data}

                try:
                    new_sit = SituationTemplate.model_validate(sit_data_with_name)
                    merged_situations[sit_name] = new_sit

                    validation_info.add_override(
                        category=ProjectOverrideCategory.SITUATION,
                        name=sit_name,
                        action=ProjectOverrideAction.ADDED,
                    )
                except ValidationError as e:
                    # Convert Pydantic validation errors
                    for error in e.errors():
                        error_field_path = ".".join(str(loc) for loc in error["loc"])
                        full_field_path = f"situations.{sit_name}.{error_field_path}"
                        message = error["msg"]
                        line_number = overlay.line_info.get_line(full_field_path)

                        validation_info.add_error(
                            field_path=full_field_path,
                            message=message,
                            line_number=line_number,
                        )

        # Merge directories
        merged_directories: dict[str, DirectoryDefinition] = {}

        for dir_name, base_dir in base.directories.items():
            if dir_name in overlay.directories:
                # Field-level merge
                merged_dir = DirectoryDefinition.merge(
                    base=base_dir,
                    overlay_data=overlay.directories[dir_name],
                    field_path=f"directories.{dir_name}",
                    validation_info=validation_info,
                    line_info=overlay.line_info,
                )
                merged_directories[dir_name] = merged_dir

                validation_info.add_override(
                    category=ProjectOverrideCategory.DIRECTORY,
                    name=dir_name,
                    action=ProjectOverrideAction.MODIFIED,
                )
            else:
                # Inherit from base
                merged_directories[dir_name] = base_dir

        # Add new directories from overlay
        for dir_name, dir_data in overlay.directories.items():
            if dir_name not in base.directories:
                # New directory - construct from scratch
                # Add name to dict for model_validate
                dir_data_with_name = {"name": dir_name, **dir_data}

                try:
                    new_dir = DirectoryDefinition.model_validate(dir_data_with_name)
                    merged_directories[dir_name] = new_dir

                    validation_info.add_override(
                        category=ProjectOverrideCategory.DIRECTORY,
                        name=dir_name,
                        action=ProjectOverrideAction.ADDED,
                    )
                except ValidationError as e:
                    # Convert Pydantic validation errors
                    for error in e.errors():
                        error_field_path = ".".join(str(loc) for loc in error["loc"])
                        full_field_path = f"directories.{dir_name}.{error_field_path}"
                        message = error["msg"]
                        line_number = overlay.line_info.get_line(full_field_path)

                        validation_info.add_error(
                            field_path=full_field_path,
                            message=message,
                            line_number=line_number,
                        )

        # Merge environment
        merged_environment = {**base.environment}
        for key, value in overlay.environment.items():
            action = ProjectOverrideAction.MODIFIED if key in base.environment else ProjectOverrideAction.ADDED
            merged_environment[key] = value

            validation_info.add_override(
                category=ProjectOverrideCategory.ENVIRONMENT,
                name=key,
                action=action,
            )

        # Use overlay metadata, fall back to base for description
        merged_description = overlay.description if overlay.description is not None else base.description

        return ProjectTemplate(
            project_template_schema_version=overlay.project_template_schema_version,
            name=overlay.name,
            situations=merged_situations,
            directories=merged_directories,
            environment=merged_environment,
            description=merged_description,
        )
