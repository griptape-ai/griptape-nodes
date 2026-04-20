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
        "griptape-nodes-previews": DirectoryDefinition(
            name="griptape-nodes-previews",
            path_macro=".griptape-nodes-previews",
        ),
        "griptape-nodes-metadata": DirectoryDefinition(
            name="griptape-nodes-metadata",
            path_macro=".griptape-nodes-metadata",
        ),
        "griptape-nodes-thumbnails": DirectoryDefinition(
            name="griptape-nodes-thumbnails",
            path_macro=".griptape-nodes-thumbnails",
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
        "save_griptape_nodes_preview": SituationTemplate(
            name="save_griptape_nodes_preview",
            description="Generate preview/thumbnail with preserved directory hierarchy",
            macro="{griptape-nodes-previews}/{drive_volume_mount?:/}{source_relative_path?:/}{source_file_name}.{preview_format}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.OVERWRITE,
                create_dirs=True,
            ),
            fallback="save_file",
        ),
        "save_static_file": SituationTemplate(
            name="save_static_file",
            description="Save static file to workflow-relative staticfiles directory. Required for projects using StaticFilesManager.save_static_file.",
            macro="{workflow_dir?:/}{static_files_dir}/{file_name_base}.{file_extension}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.OVERWRITE,
                create_dirs=True,
            ),
            fallback="save_file",
        ),
        "save_griptape_nodes_metadata": SituationTemplate(
            name="save_griptape_nodes_metadata",
            description="Save sidecar metadata file with preserved directory hierarchy",
            macro="{griptape-nodes-metadata}/{source_relative_path?:/}{source_file_name}.json",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.OVERWRITE,
                create_dirs=True,
            ),
            fallback="save_file",
        ),
        # Workflows save into the workspace root today for backward compatibility.
        # Migrating to a dedicated subdirectory is tracked in
        # https://github.com/griptape-ai/griptape-nodes/issues/2047.
        "save_workflow": SituationTemplate(
            name="save_workflow",
            description="Save a workflow Python file, preserving any sub-directory hierarchy",
            macro="{workspace_dir}/{sub_dirs?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.OVERWRITE,
                create_dirs=True,
            ),
            fallback="save_file",
        ),
        "save_workflow_thumbnail": SituationTemplate(
            name="save_workflow_thumbnail",
            description="Save a workflow thumbnail image into the hidden workspace thumbnails directory",
            macro="{griptape-nodes-thumbnails}/{file_name_base}.{file_extension}",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.OVERWRITE,
                create_dirs=True,
            ),
            fallback="save_static_file",
        ),
    },
)
