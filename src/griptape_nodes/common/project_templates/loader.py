"""YAML loading with line number tracking for project templates.

Note: This module only handles YAML parsing. File I/O operations should be
handled by ProjectManager using ReadFileRequest/WriteFileRequest to ensure
proper long path handling on Windows and consistent error handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.project import ProjectTemplate
    from griptape_nodes.common.project_templates.validation import ProjectValidationInfo

# Field name constants
FIELD_NAME = "name"
FIELD_SITUATIONS = "situations"
FIELD_DIRECTORIES = "directories"
FIELD_PROJECT_TEMPLATE_SCHEMA_VERSION = "project_template_schema_version"
FIELD_ENVIRONMENT = "environment"
FIELD_DESCRIPTION = "description"

# Special constants
ROOT_FIELD_PATH = "<root>"
DEFAULT_SCHEMA_VERSION = "0.1.0"
DEFAULT_PROJECT_NAME = "Invalid Project"


@dataclass
class YAMLLineInfo:
    """Line number information for YAML fields."""

    field_path_to_line: dict[str, int] = field(default_factory=dict)

    def get_line(self, field_path: str) -> int | None:
        """Get line number for a field path, returns None if not tracked."""
        return self.field_path_to_line.get(field_path)

    def add_mapping(self, field_path: str, line_number: int) -> None:
        """Add a field path to line number mapping."""
        self.field_path_to_line[field_path] = line_number


class YAMLParseResult(NamedTuple):
    """Result of parsing YAML with line tracking.

    Contains the parsed YAML data and line number tracking information.
    """

    data: dict[str, Any]
    line_info: YAMLLineInfo


class ProjectOverlayData(NamedTuple):
    """Partially validated project template data for merging.

    Contains raw dicts for situations/directories with basic structural validation.
    Line tracking preserved for error reporting during merge.
    Used as overlay input to ProjectTemplate.merge().
    """

    name: str
    project_template_schema_version: str
    situations: dict[str, dict[str, Any]]  # situation_name -> raw dict
    directories: dict[str, dict[str, Any]]  # directory_name -> raw dict
    environment: dict[str, str]
    description: str | None
    line_info: YAMLLineInfo


def load_yaml_with_line_tracking(yaml_text: str) -> YAMLParseResult:
    """Load YAML preserving line numbers and comments.

    Uses ruamel.yaml to parse while tracking line numbers for each field.

    Returns:
        - Parsed YAML data as dict
        - Line number tracking info

    Raises:
        YAMLError: If YAML syntax is invalid (unclosed quotes, invalid structure, etc.)
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    # Parse YAML with line tracking
    # ruamel.yaml returns CommentedMap/CommentedSeq objects with line info
    data = yaml.load(yaml_text)

    if not isinstance(data, dict):
        msg = f"Expected YAML root to be a mapping (dict), got {type(data).__name__}"
        raise YAMLError(msg)

    # Build line number mapping
    line_info = YAMLLineInfo()

    def track_lines(obj: CommentedMap | CommentedSeq, path: str) -> None:
        """Recursively track line numbers for YAML objects.

        Args:
            obj: CommentedMap or CommentedSeq from ruamel.yaml (has lc attribute)
            path: Current field path for tracking

        Note: Only CommentedMap/CommentedSeq objects have line tracking.
        Plain dicts/lists and scalars don't have lc attributes.
        """
        # Track line number for this object
        line = obj.lc.line + 1  # Convert to 1-indexed
        line_info.add_mapping(path, line)

        # Recurse into children
        if isinstance(obj, CommentedMap):
            for key, value in obj.items():
                child_path = f"{path}.{key}" if path else key
                if isinstance(value, CommentedMap | CommentedSeq):
                    track_lines(value, child_path)
        elif isinstance(obj, CommentedSeq):
            for i, item in enumerate(obj):
                child_path = f"{path}[{i}]"
                if isinstance(item, CommentedMap | CommentedSeq):
                    track_lines(item, child_path)

    # At runtime, data is a CommentedMap from ruamel.yaml
    if isinstance(data, CommentedMap):
        track_lines(data, "")

    return YAMLParseResult(data=data, line_info=line_info)


def load_project_template_from_yaml(  # noqa: C901
    yaml_text: str,
    validation_info: ProjectValidationInfo,
) -> ProjectTemplate | None:
    """Parse project.yml text into ProjectTemplate.

    Two-pass approach:
    1. Load raw YAML with line tracking (may raise YAMLError)
    2. Build ProjectTemplate via Pydantic validation, collecting validation problems

    Args:
        yaml_text: YAML text to parse
        validation_info: Validation info to populate (caller-owned, will be mutated)

    Returns:
        ProjectTemplate on success, None if fatal errors prevent construction
    """
    # Lazy import required: circular dependency between this module and project.py
    # project.py imports ProjectOverlayData from this file, and we need ProjectTemplate from project.py
    from griptape_nodes.common.project_templates.project import ProjectTemplate

    # Pass 1: Load YAML with line tracking
    try:
        result = load_yaml_with_line_tracking(yaml_text)
    except YAMLError as e:
        # YAML syntax error - cannot proceed
        validation_info.add_error(
            field_path=ROOT_FIELD_PATH,
            message=f"YAML syntax error: {e}",
            line_number=None,
        )
        return None

    # Pass 2: Build ProjectTemplate with Pydantic validation
    data = result.data
    line_info = result.line_info

    # Add names to situations and directories before validation
    if FIELD_SITUATIONS in data and isinstance(data[FIELD_SITUATIONS], dict):
        for sit_name, sit_data in data[FIELD_SITUATIONS].items():
            if isinstance(sit_data, dict):
                sit_data[FIELD_NAME] = sit_name

    if FIELD_DIRECTORIES in data and isinstance(data[FIELD_DIRECTORIES], dict):
        for dir_name, dir_data in data[FIELD_DIRECTORIES].items():
            if isinstance(dir_data, dict):
                dir_data[FIELD_NAME] = dir_name

    try:
        template = ProjectTemplate.model_validate(data)
    except ValidationError as e:
        # Convert Pydantic validation errors to our validation_info format
        for error in e.errors():
            # Build field path from error location
            field_path = ".".join(str(loc) for loc in error["loc"])
            message = error["msg"]

            # Try to get line number from our line tracking
            line_number = line_info.get_line(field_path)

            validation_info.add_error(
                field_path=field_path,
                message=message,
                line_number=line_number,
            )

        return None
    else:
        # Add warnings for schema version mismatches
        if template.project_template_schema_version != ProjectTemplate.LATEST_SCHEMA_VERSION:
            message = (
                f"Schema version '{template.project_template_schema_version}' "
                f"differs from latest '{ProjectTemplate.LATEST_SCHEMA_VERSION}'"
            )
            validation_info.add_warning(
                field_path=FIELD_PROJECT_TEMPLATE_SCHEMA_VERSION,
                message=message,
                line_number=line_info.get_line(FIELD_PROJECT_TEMPLATE_SCHEMA_VERSION),
            )

        return template


def load_partial_project_template(
    yaml_text: str,
    validation_info: ProjectValidationInfo,
) -> ProjectOverlayData | None:
    """Load project template overlay for merging without full construction.

    Performs minimal structural validation:
    - YAML syntax
    - Required top-level fields (name, project_template_schema_version)
    - Basic type checking (situations is dict, directories is dict, etc.)

    Does NOT:
    - Construct full SituationTemplate/DirectoryDefinition objects
    - Validate situation macros or policy values
    - Check directory references

    Use this for loading user overlay templates before merge.
    After merge, full validation happens during object construction.

    Args:
        yaml_text: YAML text to parse
        validation_info: Validation info to populate (caller-owned, will be mutated)

    Returns:
        ProjectOverlayData on success, None if fatal errors prevent construction
    """
    # Parse YAML with line tracking
    try:
        result = load_yaml_with_line_tracking(yaml_text)
        data = result.data
        line_info = result.line_info
    except YAMLError as e:
        validation_info.add_error(
            field_path=ROOT_FIELD_PATH,
            message=f"YAML syntax error: {e}",
            line_number=None,
        )
        return None

    # Validate required field: name
    name = data.get(FIELD_NAME)
    if name is None:
        validation_info.add_error(
            field_path=FIELD_NAME,
            message=f"Required field '{FIELD_NAME}' missing",
            line_number=line_info.get_line(FIELD_NAME),
        )
        name = DEFAULT_PROJECT_NAME
    elif not isinstance(name, str):
        validation_info.add_error(
            field_path=FIELD_NAME,
            message=f"Field '{FIELD_NAME}' must be string, got {type(name).__name__}",
            line_number=line_info.get_line(FIELD_NAME),
        )
        name = DEFAULT_PROJECT_NAME

    # Validate required field: project_template_schema_version
    schema_version = data.get(FIELD_PROJECT_TEMPLATE_SCHEMA_VERSION)
    if schema_version is None:
        validation_info.add_error(
            field_path=FIELD_PROJECT_TEMPLATE_SCHEMA_VERSION,
            message=f"Required field '{FIELD_PROJECT_TEMPLATE_SCHEMA_VERSION}' missing",
            line_number=line_info.get_line(FIELD_PROJECT_TEMPLATE_SCHEMA_VERSION),
        )
        schema_version = DEFAULT_SCHEMA_VERSION
    elif not isinstance(schema_version, str):
        validation_info.add_error(
            field_path=FIELD_PROJECT_TEMPLATE_SCHEMA_VERSION,
            message=f"Must be string, got {type(schema_version).__name__}",
            line_number=line_info.get_line(FIELD_PROJECT_TEMPLATE_SCHEMA_VERSION),
        )
        schema_version = DEFAULT_SCHEMA_VERSION

    # Optional field: situations (default to empty dict)
    situations = data.get(FIELD_SITUATIONS, {})
    if not isinstance(situations, dict):
        validation_info.add_error(
            field_path=FIELD_SITUATIONS,
            message=f"Must be dict, got {type(situations).__name__}",
            line_number=line_info.get_line(FIELD_SITUATIONS),
        )
        situations = {}

    # Optional field: directories (default to empty dict)
    directories = data.get(FIELD_DIRECTORIES, {})
    if not isinstance(directories, dict):
        validation_info.add_error(
            field_path=FIELD_DIRECTORIES,
            message=f"Must be dict, got {type(directories).__name__}",
            line_number=line_info.get_line(FIELD_DIRECTORIES),
        )
        directories = {}

    # Optional field: environment (default to empty dict)
    environment = data.get(FIELD_ENVIRONMENT, {})
    if not isinstance(environment, dict):
        validation_info.add_error(
            field_path=FIELD_ENVIRONMENT,
            message=f"Must be dict, got {type(environment).__name__}",
            line_number=line_info.get_line(FIELD_ENVIRONMENT),
        )
        environment = {}

    # Optional field: description
    description = data.get(FIELD_DESCRIPTION)
    if description is not None and not isinstance(description, str):
        validation_info.add_error(
            field_path=FIELD_DESCRIPTION,
            message=f"Must be string, got {type(description).__name__}",
            line_number=line_info.get_line(FIELD_DESCRIPTION),
        )
        description = None

    return ProjectOverlayData(
        name=name,
        project_template_schema_version=schema_version,
        situations=situations,
        directories=directories,
        environment=environment,
        description=description,
        line_info=line_info,
    )
