"""Project template main class."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, Field, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

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

    def to_overlay_yaml(self, base: ProjectTemplate) -> str:  # noqa: C901, PLR0912, PLR0915
        """Export only user customizations relative to a base template as YAML.

        Produces a minimal overlay containing only what differs from the base
        (system defaults). Content identical to the base is omitted, keeping
        the file focused on the user's actual changes.

        Sections with no user content are omitted entirely.
        Field-level diffing for situations: only changed fields are written.

        Note: deletions of optional fields (fallback, description) that exist
        in the base are not preserved — they will reappear on next load.
        """

        def q(s: str) -> DoubleQuotedScalarString:
            return DoubleQuotedScalarString(s)

        yaml = YAML()
        yaml.default_flow_style = False
        yaml.width = 4096

        data: CommentedMap = CommentedMap()
        data["project_template_schema_version"] = q(self.project_template_schema_version)
        data["name"] = q(self.name)
        if self.description is not None:
            data["description"] = q(self.description)

        # environment: only entries not in base or with a different value
        user_env: dict[str, str] = {k: v for k, v in self.environment.items() if base.environment.get(k) != v}
        if user_env:
            env: CommentedMap = CommentedMap()
            for k, v in user_env.items():
                env[k] = q(v)
            data["environment"] = env
            data.yaml_set_comment_before_after_key("environment", before="\n")

        # directories: only entries added or whose path_macro changed
        user_dirs: CommentedMap = CommentedMap()
        for dir_name, dir_def in self.directories.items():
            base_dir = base.directories.get(dir_name)
            if base_dir is None or dir_def.path_macro != base_dir.path_macro:
                entry: CommentedMap = CommentedMap()
                entry["path_macro"] = q(dir_def.path_macro)
                user_dirs[dir_name] = entry
        if user_dirs:
            data["directories"] = user_dirs
            data.yaml_set_comment_before_after_key("directories", before="\n")

        # situations: only entries added or with at least one changed field
        user_sits: CommentedMap = CommentedMap()
        first_sit = True
        for sit_name, sit in self.situations.items():
            base_sit = base.situations.get(sit_name)
            if base_sit is None:
                # Brand-new situation — include all fields
                entry = CommentedMap()
                entry["macro"] = q(sit.macro)
                policy: CommentedMap = CommentedMap()
                policy["on_collision"] = str(sit.policy.on_collision)
                policy["create_dirs"] = sit.policy.create_dirs
                entry["policy"] = policy
                if sit.fallback is not None:
                    entry["fallback"] = sit.fallback
                if sit.description is not None:
                    entry["description"] = q(sit.description)
            else:
                # Existing situation — only include fields that changed
                sit_diff: CommentedMap = CommentedMap()
                if sit.macro != base_sit.macro:
                    sit_diff["macro"] = q(sit.macro)
                policy_changed = (
                    sit.policy.on_collision != base_sit.policy.on_collision
                    or sit.policy.create_dirs != base_sit.policy.create_dirs
                )
                if policy_changed:
                    p: CommentedMap = CommentedMap()
                    p["on_collision"] = str(sit.policy.on_collision)
                    p["create_dirs"] = sit.policy.create_dirs
                    sit_diff["policy"] = p
                if sit.fallback != base_sit.fallback and sit.fallback is not None:
                    sit_diff["fallback"] = sit.fallback
                if sit.description != base_sit.description and sit.description is not None:
                    sit_diff["description"] = q(sit.description)
                if not sit_diff:
                    continue  # Identical to base — skip
                entry = sit_diff

            user_sits[sit_name] = entry
            if not first_sit:
                user_sits.yaml_set_comment_before_after_key(sit_name, before="\n")
            first_sit = False

        if user_sits:
            data["situations"] = user_sits
            data.yaml_set_comment_before_after_key("situations", before="\n")

        stream = io.StringIO()
        yaml.dump(data, stream)
        yaml_text = stream.getvalue()

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
