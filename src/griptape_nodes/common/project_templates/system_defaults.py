"""System default project template loader and accessors.

Note: System defaults are internal bundled resources (part of the package),
so direct file I/O is acceptable here. User project.yml files should be loaded
by ProjectManager using ReadFileRequest for proper long path handling.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

from ruamel.yaml import YAML

from griptape_nodes.common.project_templates.loader import load_project_template_from_yaml
from griptape_nodes.common.project_templates.validation import ProjectValidationStatus

if TYPE_CHECKING:
    from griptape_nodes.common.project_templates.directory import DirectoryDefinition
    from griptape_nodes.common.project_templates.project import ProjectTemplate
    from griptape_nodes.common.project_templates.situation import SituationTemplate

# Path to system defaults YAML file (internal bundled resource)
_DEFAULTS_DIR = Path(__file__).parent / "defaults"
_DEFAULT_PROJECT_YAML_PATH = _DEFAULTS_DIR / "project_template.yml"

# Load the default template at module import - FAIL FAST if invalid
# Direct file I/O is acceptable here since this is an internal bundled resource
_default_yaml_text = _DEFAULT_PROJECT_YAML_PATH.read_text(encoding="utf-8")
DEFAULT_PROJECT_TEMPLATE: ProjectTemplate = load_project_template_from_yaml(_default_yaml_text)

# Validate defaults - fail fast on any errors
if DEFAULT_PROJECT_TEMPLATE.validation_info.status == ProjectValidationStatus.UNUSABLE:
    error_messages = "\n".join(
        f"  Line {p.line_number}: {p.field_path} - {p.message}"
        for p in DEFAULT_PROJECT_TEMPLATE.validation_info.problems
    )
    msg = f"System default project template is invalid:\n{error_messages}"
    raise RuntimeError(msg)

if DEFAULT_PROJECT_TEMPLATE.validation_info.status == ProjectValidationStatus.MISSING:
    msg = f"System default project template not found at: {_DEFAULT_PROJECT_YAML_PATH}"
    raise RuntimeError(msg)

# Convenience accessors to situations and directories
SYSTEM_DEFAULT_SITUATIONS: dict[str, SituationTemplate] = DEFAULT_PROJECT_TEMPLATE.situations
DEFAULT_DIRECTORIES: dict[str, DirectoryDefinition] = DEFAULT_PROJECT_TEMPLATE.directories

# Individual situation accessors for convenience
DEFAULT_SAVE_FILE: SituationTemplate = SYSTEM_DEFAULT_SITUATIONS["save_file"]
DEFAULT_COPY_EXTERNAL_FILE: SituationTemplate = SYSTEM_DEFAULT_SITUATIONS["copy_external_file"]
DEFAULT_DOWNLOAD_URL: SituationTemplate = SYSTEM_DEFAULT_SITUATIONS["download_url"]
DEFAULT_SAVE_NODE_OUTPUT: SituationTemplate = SYSTEM_DEFAULT_SITUATIONS["save_node_output"]
DEFAULT_SAVE_PREVIEW: SituationTemplate = SYSTEM_DEFAULT_SITUATIONS["save_preview"]


def get_default_project_template() -> ProjectTemplate:
    """Get a copy of the system default project template.

    Returns:
        ProjectTemplate with GOOD validation status (guaranteed by module load)
    """
    return DEFAULT_PROJECT_TEMPLATE


def export_default_project_yaml() -> str:
    """Export default project template as YAML string for new projects.

    Returns the raw YAML from defaults/project_template.yml with comments preserved.
    """
    return _DEFAULT_PROJECT_YAML_PATH.read_text(encoding="utf-8")


def export_situation_yaml(situation_name: str) -> str:
    """Export a single situation as YAML snippet.

    Useful for documentation or letting users copy individual situations.

    Args:
        situation_name: Name of situation to export

    Returns:
        YAML string for just that situation

    Raises:
        KeyError: If situation_name not found in system defaults
    """
    if situation_name not in SYSTEM_DEFAULT_SITUATIONS:
        available = ", ".join(sorted(SYSTEM_DEFAULT_SITUATIONS.keys()))
        msg = f"Situation '{situation_name}' not found in system defaults. Available: {available}"
        raise KeyError(msg)

    situation = SYSTEM_DEFAULT_SITUATIONS[situation_name]

    # Convert to YAML
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    stream = io.StringIO()
    yaml.dump({situation_name: situation.to_dict()}, stream)
    return stream.getvalue()


def get_situation_with_fallback(
    situation_name: str,
    project_template: ProjectTemplate | None = None,
) -> SituationTemplate:
    """Get situation from project or fall back to system default.

    Follows fallback chain if situation not found in project.
    Falls back to system defaults if not in project or fallback chain fails.

    Args:
        situation_name: Name of situation to retrieve
        project_template: Optional project template to search first

    Returns:
        SituationTemplate (always succeeds - system defaults guarantee existence)
    """
    # Try project template first
    if project_template is not None:
        situation = project_template.get_situation(situation_name)
        if situation is not None:
            return situation

        # Not found - check if any situation has this as a fallback
        # Follow fallback chain
        for candidate_situation in project_template.situations.values():
            if candidate_situation.fallback == situation_name and candidate_situation.fallback is not None:
                # Found a situation that falls back to this one
                # Try to get it from the project or system
                fallback_situation = project_template.get_situation(candidate_situation.fallback)
                if fallback_situation is not None:
                    return fallback_situation

    # Fall back to system defaults
    if situation_name in SYSTEM_DEFAULT_SITUATIONS:
        return SYSTEM_DEFAULT_SITUATIONS[situation_name]

    # Not found in system defaults - follow fallback chain in system defaults
    for candidate_situation in SYSTEM_DEFAULT_SITUATIONS.values():
        if candidate_situation.name == situation_name:
            # Found it
            return candidate_situation
        if (
            candidate_situation.fallback == situation_name
            and candidate_situation.fallback
            and candidate_situation.fallback in SYSTEM_DEFAULT_SITUATIONS
        ):
            # Follow the fallback
            return SYSTEM_DEFAULT_SITUATIONS[candidate_situation.fallback]

    # Ultimate fallback - return save_file (base situation)
    return DEFAULT_SAVE_FILE
