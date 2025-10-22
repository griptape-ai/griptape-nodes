"""Project template main class."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from ruamel.yaml import YAML

from griptape_nodes.common.project_templates.directory import DirectoryDefinition
from griptape_nodes.common.project_templates.situation import SituationTemplate
from griptape_nodes.common.project_templates.validation import ProjectValidationInfo, ProjectValidationStatus

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.loader import YAMLLineInfo


@dataclass
class ProjectTemplate:
    """Complete project template loaded from project.yml."""

    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.1.0"

    project_template_schema_version: str
    name: str
    situations: dict[str, SituationTemplate]  # situation_name -> template
    directories: dict[str, DirectoryDefinition]  # logical_name -> definition
    environment: dict[str, str]  # Custom environment variables
    description: str | None = None

    validation_info: ProjectValidationInfo = field(
        default_factory=lambda: ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
    )

    @staticmethod
    def from_dict(  # noqa: C901, PLR0912, PLR0915
        data: dict[str, Any],
        validation_info: ProjectValidationInfo,
        line_info: YAMLLineInfo,
    ) -> ProjectTemplate:
        """Construct from YAML dict, validating and populating validation_info.

        Validates:
        - Project schema version compatibility
        - Required top-level fields present
        - Situations dict (delegates to SituationTemplate.from_dict)
        - Directories dict (delegates to DirectoryDefinition.from_dict)
        - Environment dict contains only string values

        Returns ProjectTemplate even if validation fails (fault-tolerant).
        """
        # Extract and validate project schema version
        schema_version = data.get("project_template_schema_version")
        if schema_version is None:
            validation_info.add_error(
                field_path="project_template_schema_version",
                message="Missing required field 'project_template_schema_version'",
                line_number=line_info.get_line(""),
            )
            schema_version = ProjectTemplate.LATEST_SCHEMA_VERSION  # Fallback
        elif schema_version != ProjectTemplate.LATEST_SCHEMA_VERSION:
            validation_info.add_warning(
                field_path="project_template_schema_version",
                message=f"Schema version '{schema_version}' differs from latest '{ProjectTemplate.LATEST_SCHEMA_VERSION}'",
                line_number=line_info.get_line("project_template_schema_version"),
            )

        # Extract name
        name = data.get("name")
        if name is None:
            validation_info.add_error(
                field_path="name",
                message="Missing required field 'name'",
                line_number=line_info.get_line(""),
            )
            name = "Unnamed Project"  # Fallback
        elif not isinstance(name, str):
            validation_info.add_error(
                field_path="name",
                message=f"Field 'name' must be string, got {type(name).__name__}",
                line_number=line_info.get_line("name"),
            )
            name = "Invalid Project"  # Fallback

        # Extract situations dict
        situations_data = data.get("situations")
        situations: dict[str, SituationTemplate] = {}
        if situations_data is None:
            validation_info.add_error(
                field_path="situations",
                message="Missing required field 'situations'",
                line_number=line_info.get_line(""),
            )
        elif not isinstance(situations_data, dict):
            validation_info.add_error(
                field_path="situations",
                message=f"Field 'situations' must be dict, got {type(situations_data).__name__}",
                line_number=line_info.get_line("situations"),
            )
        else:
            # Parse each situation
            for situation_name, situation_data in situations_data.items():
                if not isinstance(situation_data, dict):
                    validation_info.add_error(
                        field_path=f"situations.{situation_name}",
                        message=f"Situation must be dict, got {type(situation_data).__name__}",
                        line_number=line_info.get_line(f"situations.{situation_name}"),
                    )
                    continue

                # Add name to situation data for construction
                situation_data_with_name = {**situation_data, "name": situation_name}
                situation = SituationTemplate.from_dict(
                    situation_data_with_name,
                    f"situations.{situation_name}",
                    validation_info,
                    line_info,
                )
                situations[situation_name] = situation

        # Extract directories dict
        directories_data = data.get("directories")
        directories: dict[str, DirectoryDefinition] = {}
        if directories_data is None:
            validation_info.add_error(
                field_path="directories",
                message="Missing required field 'directories'",
                line_number=line_info.get_line(""),
            )
        elif not isinstance(directories_data, dict):
            validation_info.add_error(
                field_path="directories",
                message=f"Field 'directories' must be dict, got {type(directories_data).__name__}",
                line_number=line_info.get_line("directories"),
            )
        else:
            # Parse each directory
            for dir_name, dir_data in directories_data.items():
                if not isinstance(dir_data, dict):
                    validation_info.add_error(
                        field_path=f"directories.{dir_name}",
                        message=f"Directory must be dict, got {type(dir_data).__name__}",
                        line_number=line_info.get_line(f"directories.{dir_name}"),
                    )
                    continue

                # Add name to directory data for construction
                dir_data_with_name = {**dir_data, "name": dir_name}
                directory = DirectoryDefinition.from_dict(
                    dir_data_with_name,
                    f"directories.{dir_name}",
                    validation_info,
                    line_info,
                )
                directories[dir_name] = directory

        # Extract environment dict (optional)
        environment_data = data.get("environment", {})
        environment: dict[str, str] = {}
        if not isinstance(environment_data, dict):
            validation_info.add_error(
                field_path="environment",
                message=f"Field 'environment' must be dict, got {type(environment_data).__name__}",
                line_number=line_info.get_line("environment"),
            )
        else:
            # Validate all values are strings
            for env_key, env_value in environment_data.items():
                if not isinstance(env_value, str):
                    validation_info.add_error(
                        field_path=f"environment.{env_key}",
                        message=f"Environment value must be string, got {type(env_value).__name__}",
                        line_number=line_info.get_line(f"environment.{env_key}"),
                    )
                else:
                    environment[env_key] = env_value

        # Extract description (optional)
        description = data.get("description")
        if description is not None and not isinstance(description, str):
            validation_info.add_error(
                field_path="description",
                message=f"Field 'description' must be string, got {type(description).__name__}",
                line_number=line_info.get_line("description"),
            )
            description = None

        return ProjectTemplate(
            project_template_schema_version=schema_version,
            name=name,
            situations=situations,
            directories=directories,
            environment=environment,
            description=description,
            validation_info=validation_info,
        )

    def get_situation(self, situation_name: str) -> SituationTemplate | None:
        """Get a situation by name, returns None if not found."""
        return self.situations.get(situation_name)

    def get_directory(self, directory_name: str) -> DirectoryDefinition | None:
        """Get a directory definition by logical name."""
        return self.directories.get(directory_name)

    def is_valid(self) -> bool:
        """Check if template is valid (GOOD or FLAWED status)."""
        return self.validation_info.status in (ProjectValidationStatus.GOOD, ProjectValidationStatus.FLAWED)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary suitable for YAML export."""
        result: dict[str, Any] = {
            "project_template_schema_version": self.project_template_schema_version,
            "name": self.name,
            "directories": {name: dir_def.to_dict() for name, dir_def in self.directories.items()},
            "environment": self.environment,
            "situations": {name: situation.to_dict() for name, situation in self.situations.items()},
        }

        if self.description is not None:
            result["description"] = self.description

        return result

    def to_yaml(self, *, include_comments: bool = True) -> str:
        """Export project template to YAML string.

        If include_comments=True, adds helpful comments explaining each section.
        """
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False

        data = self.to_dict()

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
