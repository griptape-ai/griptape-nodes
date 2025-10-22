"""Project template system for managing project.yml files and situations."""

from pathlib import Path

from griptape_nodes.common.project_templates.directory import DirectoryDefinition
from griptape_nodes.common.project_templates.loader import (
    ProjectOverlayData,
    YAMLLineInfo,
    YAMLParseResult,
    load_partial_project_template,
    load_project_template_from_yaml,
    load_yaml_with_line_tracking,
)
from griptape_nodes.common.project_templates.project import ProjectTemplate
from griptape_nodes.common.project_templates.situation import (
    SituationFilePolicy,
    SituationPolicy,
    SituationTemplate,
)
from griptape_nodes.common.project_templates.validation import (
    ProjectOverride,
    ProjectOverrideAction,
    ProjectOverrideCategory,
    ProjectValidationInfo,
    ProjectValidationProblem,
    ProjectValidationProblemSeverity,
    ProjectValidationStatus,
)

# Path to bundled system default project template
# ProjectManager is responsible for loading this file
DEFAULT_PROJECT_YAML_PATH = Path(__file__).parent / "defaults" / "project_template.yml"

__all__ = [
    "DEFAULT_PROJECT_YAML_PATH",
    "DirectoryDefinition",
    "ProjectOverlayData",
    "ProjectOverride",
    "ProjectOverrideAction",
    "ProjectOverrideCategory",
    "ProjectTemplate",
    "ProjectValidationInfo",
    "ProjectValidationProblem",
    "ProjectValidationProblemSeverity",
    "ProjectValidationStatus",
    "SituationFilePolicy",
    "SituationPolicy",
    "SituationTemplate",
    "YAMLLineInfo",
    "YAMLParseResult",
    "load_partial_project_template",
    "load_project_template_from_yaml",
    "load_yaml_with_line_tracking",
]
