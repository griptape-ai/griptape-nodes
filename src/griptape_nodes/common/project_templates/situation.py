"""Situation template definitions for file path scenarios."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.loader import YAMLLineInfo
    from griptape_nodes.common.project_templates.validation import ProjectValidationInfo


class SituationFilePolicy(StrEnum):
    """Policy for handling file collisions in situations.

    Maps to ExistingFilePolicy for file operations, except PROMPT which
    triggers user interaction before determining final policy.
    """

    CREATE_NEW = "create_new"  # Increment {_index} in macro
    OVERWRITE = "overwrite"  # Maps to ExistingFilePolicy.OVERWRITE
    FAIL = "fail"  # Maps to ExistingFilePolicy.FAIL
    PROMPT = "prompt"  # Special UI handling


class SituationPolicy(BaseModel):
    """Policy for file operations in a situation."""

    on_collision: SituationFilePolicy = Field(description="Policy for handling file collisions")
    create_dirs: bool = Field(description="Whether to create directories automatically")


class SituationTemplate(BaseModel):
    """Template defining how files are saved in a specific situation."""

    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.1.0"

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Name of the situation")
    situation_template_schema_version: str = Field(description="Schema version for this situation template")
    macro: str = Field(description="Macro template for file path")
    policy: SituationPolicy = Field(description="Policy for file operations")
    fallback: str | None = Field(default=None, description="Name of fallback situation")
    description: str | None = Field(default=None, description="Description of the situation")

    @field_validator("macro")
    @classmethod
    def validate_macro_syntax(cls, v: str) -> str:
        """Validate macro syntax using macro parser."""
        try:
            ParsedMacro(v)
        except MacroSyntaxError as e:
            msg = f"Invalid macro syntax: {e}"
            raise ValueError(msg) from e
        return v

    @staticmethod
    def merge(
        base: SituationTemplate,
        overlay_data: dict[str, Any],
        field_path: str,
        validation_info: ProjectValidationInfo,
        line_info: YAMLLineInfo,
    ) -> SituationTemplate:
        """Merge overlay fields onto base situation.

        Field-level merge behavior:
        - macro: Use overlay if present, else base
        - description: Use overlay if present, else base
        - fallback: Use overlay if present, else base
        - policy: Use overlay if present (must be complete), else base
        - situation_template_schema_version: Use overlay if present, else base

        Policy validation:
        - If policy provided in overlay, must contain both on_collision and create_dirs
        - Adds error to validation_info if incomplete

        Args:
            base: Complete base situation to start from
            overlay_data: Partial situation dict from overlay YAML
            field_path: Path for validation errors (e.g., "situations.save_file")
            validation_info: Shared validation info
            line_info: Line tracking from overlay YAML

        Returns:
            New merged SituationTemplate
        """
        # Start with base fields as dict
        merged_data = base.model_dump()

        # Apply overlay fields if present
        if "macro" in overlay_data:
            merged_data["macro"] = overlay_data["macro"]

        if "description" in overlay_data:
            merged_data["description"] = overlay_data["description"]

        if "fallback" in overlay_data:
            merged_data["fallback"] = overlay_data["fallback"]

        if "situation_template_schema_version" in overlay_data:
            merged_data["situation_template_schema_version"] = overlay_data["situation_template_schema_version"]

        # Policy must be complete if provided
        if "policy" in overlay_data:
            policy = overlay_data["policy"]
            if not isinstance(policy, dict):
                validation_info.add_error(
                    field_path=f"{field_path}.policy",
                    message="Policy must be a dict",
                    line_number=line_info.get_line(f"{field_path}.policy"),
                )
            elif "on_collision" not in policy or "create_dirs" not in policy:
                validation_info.add_error(
                    field_path=f"{field_path}.policy",
                    message="Policy must include both on_collision and create_dirs",
                    line_number=line_info.get_line(f"{field_path}.policy"),
                )
            else:
                merged_data["policy"] = policy

        # Build merged situation using model_validate
        # Note: name field is not in overlay_data, use base.name
        merged_data_with_name = {"name": base.name, **merged_data}

        try:
            return SituationTemplate.model_validate(merged_data_with_name)
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
