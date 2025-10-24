"""Default project template defined in Python using Pydantic models."""

from griptape_nodes.common.project_templates.directory import DirectoryDefinition
from griptape_nodes.common.project_templates.project import ProjectTemplate
from griptape_nodes.common.project_templates.situation import (
    SituationFilePolicy,
    SituationPolicy,
    SituationTemplate,
)

# Default project template matching the values from project_template.yml
DEFAULT_PROJECT_TEMPLATE = ProjectTemplate(
    project_template_schema_version="0.1.0",
    name="Default Project",
    description="System default configuration",
    directories={
        "inputs": DirectoryDefinition(
            name="inputs",
            path_schema="inputs",
        ),
        "outputs": DirectoryDefinition(
            name="outputs",
            path_schema="outputs",
        ),
        "temp": DirectoryDefinition(
            name="temp",
            path_schema="temp",
        ),
        "previews": DirectoryDefinition(
            name="previews",
            path_schema="previews",
        ),
    },
    environment={},
    situations={
        "save_file": SituationTemplate(
            name="save_file",
            situation_template_schema_version="0.1.0",
            description="Generic file save operation",
            macro="{file_name_base}{_index?:03}.{file_extension}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.CREATE_NEW,
                create_dirs=True,
            ),
            fallback=None,
        ),
        "copy_external_file": SituationTemplate(
            name="copy_external_file",
            situation_template_schema_version="0.1.0",
            description="User copies external file to project",
            macro="{inputs}/{node_name?:_}{parameter_name?:_}{file_name_base}{_index?:03}.{file_extension}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.CREATE_NEW,
                create_dirs=True,
            ),
            fallback="save_file",
        ),
        "download_url": SituationTemplate(
            name="download_url",
            situation_template_schema_version="0.1.0",
            description="Download file from URL",
            macro="{inputs}/{sanitized_url}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.OVERWRITE,
                create_dirs=True,
            ),
            fallback="save_file",
        ),
        "save_node_output": SituationTemplate(
            name="save_node_output",
            situation_template_schema_version="0.1.0",
            description="Node generates and saves output",
            macro="{outputs}/{node_name?:_}{file_name_base}{_index?:03}.{file_extension}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.CREATE_NEW,
                create_dirs=True,
            ),
            fallback="save_file",
        ),
        "save_preview": SituationTemplate(
            name="save_preview",
            situation_template_schema_version="0.1.0",
            description="Generate preview/thumbnail",
            macro="{previews}/{original_file_path}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.OVERWRITE,
                create_dirs=True,
            ),
            fallback="save_file",
        ),
    },
)
