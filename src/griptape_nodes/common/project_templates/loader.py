"""YAML loading with line number tracking for project templates.

Note: This module only handles YAML parsing. File I/O operations should be
handled by ProjectManager using ReadFileRequest/WriteFileRequest to ensure
proper long path handling on Windows and consistent error handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

from griptape_nodes.common.project_templates.validation import ProjectValidationStatus

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.project import ProjectTemplate


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


def load_yaml_with_line_tracking(yaml_text: str) -> tuple[dict[str, Any], YAMLLineInfo]:
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

    return data, line_info


def load_project_template_from_yaml(yaml_text: str) -> ProjectTemplate:
    """Parse project.yml text into ProjectTemplate.

    Two-pass approach:
    1. Load raw YAML with line tracking (may raise YAMLError)
    2. Build ProjectTemplate via from_dict(), collecting validation problems

    Returns ProjectTemplate with validation_info populated.
    Status will be GOOD, FLAWED, or UNUSABLE depending on problems found.
    """
    # Lazy import required: circular dependency between this module and project module
    # loader imports from project, project imports from directory/situation, which import YAMLLineInfo from loader
    from griptape_nodes.common.project_templates.project import ProjectTemplate
    from griptape_nodes.common.project_templates.validation import ProjectValidationInfo

    # Pass 1: Load YAML with line tracking
    try:
        data, line_info = load_yaml_with_line_tracking(yaml_text)
    except YAMLError as e:
        # YAML syntax error - return UNUSABLE template
        validation_info = ProjectValidationInfo(status=ProjectValidationStatus.UNUSABLE)
        validation_info.add_error(
            field_path="<root>",
            message=f"YAML syntax error: {e}",
            line_number=None,
        )
        # Return a minimal template with validation errors
        return ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="Invalid Project",
            situations={},
            directories={},
            environment={},
            description=None,
            validation_info=validation_info,
        )

    # Pass 2: Build ProjectTemplate with validation
    validation_info = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
    template = ProjectTemplate.from_dict(data, validation_info, line_info)

    return template
