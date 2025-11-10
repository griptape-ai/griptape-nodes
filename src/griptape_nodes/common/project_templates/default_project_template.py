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
            path_macro="inputs",
        ),
        "outputs": DirectoryDefinition(
            name="outputs",
            path_macro="outputs",
        ),
        "temp": DirectoryDefinition(
            name="temp",
            path_macro="temp",
        ),
        "previews": DirectoryDefinition(
            name="previews",
            path_macro="previews",
        ),
    },
    environment={},
    situations={
        "save_file": SituationTemplate(
            name="save_file",
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
            description="Node generates and saves output",
            macro="{outputs}/{sub_dirs?:/}{node_name?:_}{file_name_base}{_index?:03}.{file_extension}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.CREATE_NEW,
                create_dirs=True,
            ),
            fallback="save_file",
        ),
        "save_preview": SituationTemplate(
            name="save_preview",
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
