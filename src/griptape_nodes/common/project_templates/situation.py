"""Situation template definitions for file path scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.loader import YAMLLineInfo
    from griptape_nodes.common.project_templates.validation import ProjectValidationInfo


class SituationFilePolicy(StrEnum):
    """Policy for handling file collisions in situations.

    Maps to ExistingFilePolicy for file operations, except PROMPT which
    triggers user interaction before determining final policy.
    """

    CREATE_NEW = "create_new"  # Increment {_index} in schema
    OVERWRITE = "overwrite"  # Maps to ExistingFilePolicy.OVERWRITE
    FAIL = "fail"  # Maps to ExistingFilePolicy.FAIL
    PROMPT = "prompt"  # Special UI handling


@dataclass
class SituationPolicy:
    """Policy for file operations in a situation."""

    on_collision: SituationFilePolicy
    create_dirs: bool

    @staticmethod
    def from_dict(
        data: dict[str, Any],
        field_path: str,
        validation_info: ProjectValidationInfo,
        line_info: YAMLLineInfo,
    ) -> SituationPolicy:
        """Construct from YAML dict, validating and populating validation_info."""
        # Extract on_collision
        on_collision_value = data.get("on_collision")
        if on_collision_value is None:
            validation_info.add_error(
                field_path=f"{field_path}.on_collision",
                message="Missing required field 'on_collision'",
                line_number=line_info.get_line(field_path),
            )
            on_collision_value = "fail"  # Default fallback

        # Validate on_collision is valid enum value
        try:
            on_collision = SituationFilePolicy(on_collision_value)
        except ValueError:
            valid_values = ", ".join(p.value for p in SituationFilePolicy)
            validation_info.add_error(
                field_path=f"{field_path}.on_collision",
                message=f"Invalid value '{on_collision_value}', expected one of: {valid_values}",
                line_number=line_info.get_line(f"{field_path}.on_collision"),
            )
            on_collision = SituationFilePolicy.FAIL  # Default fallback

        # Extract create_dirs
        create_dirs_value = data.get("create_dirs")
        if create_dirs_value is None:
            validation_info.add_error(
                field_path=f"{field_path}.create_dirs",
                message="Missing required field 'create_dirs'",
                line_number=line_info.get_line(field_path),
            )
            create_dirs = True  # Default fallback
        elif not isinstance(create_dirs_value, bool):
            validation_info.add_error(
                field_path=f"{field_path}.create_dirs",
                message=f"Field 'create_dirs' must be boolean, got {type(create_dirs_value).__name__}",
                line_number=line_info.get_line(f"{field_path}.create_dirs"),
            )
            create_dirs = True  # Default fallback
        else:
            create_dirs = create_dirs_value

        return SituationPolicy(on_collision=on_collision, create_dirs=create_dirs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary suitable for YAML export."""
        return {
            "on_collision": self.on_collision.value,
            "create_dirs": self.create_dirs,
        }


@dataclass
class SituationTemplate:
    """Template defining how files are saved in a specific situation."""

    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.1.0"

    name: str
    situation_template_schema_version: str
    schema: str  # Macro template for file path
    policy: SituationPolicy
    fallback: str | None  # Name of fallback situation
    description: str | None = None

    @staticmethod
    def from_dict(
        data: dict[str, Any],
        field_path: str,
        validation_info: ProjectValidationInfo,
        line_info: YAMLLineInfo,
    ) -> SituationTemplate:
        """Construct from YAML dict, validating and populating validation_info.

        Validates:
        - Schema version compatibility
        - Schema syntax (balanced braces, valid format specs)
        - Policy values are valid enums
        - Required fields present

        Returns SituationTemplate even if validation fails (fault-tolerant).
        All problems added to validation_info.
        """
        # Extract name (should be provided by caller from dict key)
        name = data.get("name", "unknown")

        # Extract and validate schema version
        schema_version = data.get("situation_template_schema_version")
        if schema_version is None:
            validation_info.add_error(
                field_path=f"{field_path}.situation_template_schema_version",
                message="Missing required field 'situation_template_schema_version'",
                line_number=line_info.get_line(field_path),
            )
            schema_version = SituationTemplate.LATEST_SCHEMA_VERSION  # Fallback
        elif schema_version != SituationTemplate.LATEST_SCHEMA_VERSION:
            validation_info.add_warning(
                field_path=f"{field_path}.situation_template_schema_version",
                message=f"Schema version '{schema_version}' differs from latest '{SituationTemplate.LATEST_SCHEMA_VERSION}'",
                line_number=line_info.get_line(f"{field_path}.situation_template_schema_version"),
            )

        # Extract schema
        schema = data.get("schema")
        if schema is None:
            validation_info.add_error(
                field_path=f"{field_path}.schema",
                message="Missing required field 'schema'",
                line_number=line_info.get_line(field_path),
            )
            schema = "{file_name}"  # Fallback
        elif not isinstance(schema, str):
            validation_info.add_error(
                field_path=f"{field_path}.schema",
                message=f"Field 'schema' must be string, got {type(schema).__name__}",
                line_number=line_info.get_line(f"{field_path}.schema"),
            )
            schema = "{file_name}"  # Fallback
        else:
            # Validate schema syntax using macro parser
            try:
                ParsedMacro(schema)
            except MacroSyntaxError as e:
                validation_info.add_error(
                    field_path=f"{field_path}.schema",
                    message=f"Invalid schema syntax: {e}",
                    line_number=line_info.get_line(f"{field_path}.schema"),
                )

        # Extract policy
        policy_data = data.get("policy")
        if policy_data is None:
            validation_info.add_error(
                field_path=f"{field_path}.policy",
                message="Missing required field 'policy'",
                line_number=line_info.get_line(field_path),
            )
            policy = SituationPolicy(on_collision=SituationFilePolicy.FAIL, create_dirs=True)
        elif not isinstance(policy_data, dict):
            validation_info.add_error(
                field_path=f"{field_path}.policy",
                message=f"Field 'policy' must be dict, got {type(policy_data).__name__}",
                line_number=line_info.get_line(f"{field_path}.policy"),
            )
            policy = SituationPolicy(on_collision=SituationFilePolicy.FAIL, create_dirs=True)
        else:
            policy = SituationPolicy.from_dict(policy_data, f"{field_path}.policy", validation_info, line_info)

        # Extract fallback (optional)
        fallback = data.get("fallback")
        if fallback is not None and not isinstance(fallback, str):
            validation_info.add_error(
                field_path=f"{field_path}.fallback",
                message=f"Field 'fallback' must be string or null, got {type(fallback).__name__}",
                line_number=line_info.get_line(f"{field_path}.fallback"),
            )
            fallback = None

        # Extract description (optional)
        description = data.get("description")
        if description is not None and not isinstance(description, str):
            validation_info.add_error(
                field_path=f"{field_path}.description",
                message=f"Field 'description' must be string, got {type(description).__name__}",
                line_number=line_info.get_line(f"{field_path}.description"),
            )
            description = None

        return SituationTemplate(
            name=name,
            situation_template_schema_version=schema_version,
            schema=schema,
            policy=policy,
            fallback=fallback,
            description=description,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary suitable for YAML export."""
        result: dict[str, Any] = {
            "situation_template_schema_version": self.situation_template_schema_version,
            "schema": self.schema,
            "policy": self.policy.to_dict(),
            "fallback": self.fallback,
        }

        if self.description is not None:
            result["description"] = self.description

        return result
