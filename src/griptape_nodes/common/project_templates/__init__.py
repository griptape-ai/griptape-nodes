"""Project template system for managing project.yml files and situations."""

from griptape_nodes.common.project_templates.directory import DirectoryDefinition
from griptape_nodes.common.project_templates.loader import (
    YAMLLineInfo,
    load_project_template_from_yaml,
    load_yaml_with_line_tracking,
)
from griptape_nodes.common.project_templates.project import ProjectTemplate
from griptape_nodes.common.project_templates.situation import (
    SituationFilePolicy,
    SituationPolicy,
    SituationTemplate,
)
from griptape_nodes.common.project_templates.system_defaults import (
    DEFAULT_COPY_EXTERNAL_FILE,
    DEFAULT_DIRECTORIES,
    DEFAULT_DOWNLOAD_URL,
    DEFAULT_PROJECT_TEMPLATE,
    DEFAULT_SAVE_FILE,
    DEFAULT_SAVE_NODE_OUTPUT,
    DEFAULT_SAVE_PREVIEW,
    SYSTEM_DEFAULT_SITUATIONS,
    export_default_project_yaml,
    export_situation_yaml,
    get_default_project_template,
    get_situation_with_fallback,
)
from griptape_nodes.common.project_templates.validation import (
    ProjectValidationInfo,
    ProjectValidationProblem,
    ProjectValidationProblemSeverity,
    ProjectValidationStatus,
)

__all__ = [
    "DEFAULT_COPY_EXTERNAL_FILE",
    "DEFAULT_DIRECTORIES",
    "DEFAULT_DOWNLOAD_URL",
    "DEFAULT_PROJECT_TEMPLATE",
    "DEFAULT_SAVE_FILE",
    "DEFAULT_SAVE_NODE_OUTPUT",
    "DEFAULT_SAVE_PREVIEW",
    "SYSTEM_DEFAULT_SITUATIONS",
    "DirectoryDefinition",
    "ProjectTemplate",
    "ProjectValidationInfo",
    "ProjectValidationProblem",
    "ProjectValidationProblemSeverity",
    "ProjectValidationStatus",
    "SituationFilePolicy",
    "SituationPolicy",
    "SituationTemplate",
    "YAMLLineInfo",
    "export_default_project_yaml",
    "export_situation_yaml",
    "get_default_project_template",
    "get_situation_with_fallback",
    "load_project_template_from_yaml",
    "load_yaml_with_line_tracking",
]
