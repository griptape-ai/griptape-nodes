"""Tests for project template layering and merge functionality."""

from griptape_nodes.common.project_templates import (
    DEFAULT_PROJECT_TEMPLATE,
    ProjectOverrideAction,
    ProjectOverrideCategory,
    ProjectTemplate,
    ProjectValidationInfo,
    ProjectValidationStatus,
    load_partial_project_template,
)

# Use system defaults directly (no longer loading from YAML)
_SYSTEM_DEFAULTS = DEFAULT_PROJECT_TEMPLATE


class TestPartialLoading:
    """Tests for load_partial_project_template function."""

    def test_minimal_valid_overlay(self) -> None:
        """Test loading minimal valid overlay with just name and schema version."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Test Project"
"""
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, validation)

        assert overlay is not None
        assert validation.status == ProjectValidationStatus.GOOD
        assert overlay.name == "Test Project"
        assert overlay.project_template_schema_version == "0.1.0"
        assert overlay.situations == {}
        assert overlay.directories == {}
        assert overlay.environment == {}
        assert overlay.description is None

    def test_overlay_with_custom_situation(self) -> None:
        """Test loading overlay with custom situation definition."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
situations:
  my_situation:
    situation_template_schema_version: "0.1.0"
    schema: "{outputs}/custom.{file_extension}"
    policy:
      on_collision: "overwrite"
      create_dirs: true
    fallback: null
"""
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, validation)

        assert overlay is not None
        assert validation.status == ProjectValidationStatus.GOOD
        assert overlay.name == "Custom Project"
        assert "my_situation" in overlay.situations
        assert overlay.situations["my_situation"]["schema"] == "{outputs}/custom.{file_extension}"

    def test_overlay_with_custom_directory(self) -> None:
        """Test loading overlay with custom directory definition."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
directories:
  custom_dir:
    path_schema: "my_custom_path"
"""
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, validation)

        assert overlay is not None
        assert validation.status == ProjectValidationStatus.GOOD
        assert "custom_dir" in overlay.directories
        assert overlay.directories["custom_dir"]["path_schema"] == "my_custom_path"

    def test_overlay_with_environment(self) -> None:
        """Test loading overlay with environment variables."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
environment:
  MY_VAR: "my_value"
  ANOTHER_VAR: "another_value"
"""
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, validation)

        assert overlay is not None
        assert validation.status == ProjectValidationStatus.GOOD
        assert overlay.environment["MY_VAR"] == "my_value"
        assert overlay.environment["ANOTHER_VAR"] == "another_value"

    def test_overlay_missing_name(self) -> None:
        """Test that missing name field causes validation error."""
        yaml_text = """
project_template_schema_version: "0.1.0"
"""
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        load_partial_project_template(yaml_text, validation)

        assert validation.status == ProjectValidationStatus.UNUSABLE
        assert any("name" in p.field_path for p in validation.problems)

    def test_overlay_missing_schema_version(self) -> None:
        """Test that missing schema version causes validation error."""
        yaml_text = """
name: "Test Project"
"""
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        load_partial_project_template(yaml_text, validation)

        assert validation.status == ProjectValidationStatus.UNUSABLE
        assert any("project_template_schema_version" in p.field_path for p in validation.problems)

    def test_overlay_invalid_yaml_syntax(self) -> None:
        """Test that invalid YAML syntax is caught."""
        yaml_text = """
name: "Test Project
project_template_schema_version: "0.1.0"
"""
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, validation)

        assert overlay is None
        assert validation.status == ProjectValidationStatus.UNUSABLE
        assert any("YAML syntax error" in p.message for p in validation.problems)


class TestMerge:
    """Tests for ProjectTemplate.merge functionality."""

    def test_merge_minimal_overlay(self) -> None:
        """Test merging minimal overlay with just name override."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "My Custom Project"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        merge_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        merged = ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=merge_validation,
        )

        assert merge_validation.status == ProjectValidationStatus.GOOD
        assert merged.name == "My Custom Project"
        # Should inherit all situations from base
        assert len(merged.situations) == len(default_template.situations)
        # Should inherit all directories from base
        assert len(merged.directories) == len(default_template.directories)

    def test_merge_override_existing_situation(self) -> None:
        """Test merging overlay that modifies an existing situation."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
situations:
  save_node_output:
    schema: "{outputs}/custom_{node_name}.{file_extension}"
    policy:
      on_collision: "overwrite"
      create_dirs: true
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        merged = ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check situation was modified
        assert merged.situations["save_node_output"].schema == "{outputs}/custom_{node_name}.{file_extension}"
        # Check other situations are inherited
        assert "save_file" in merged.situations
        assert "copy_external_file" in merged.situations

    def test_merge_add_new_situation(self) -> None:
        """Test merging overlay that adds a brand new situation."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
situations:
  my_new_situation:
    situation_template_schema_version: "0.1.0"
    schema: "{outputs}/new_{file_name}.{file_extension}"
    policy:
      on_collision: "create_new"
      create_dirs: true
    fallback: "save_file"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        merged = ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check new situation was added
        assert "my_new_situation" in merged.situations
        assert merged.situations["my_new_situation"].schema == "{outputs}/new_{file_name}.{file_extension}"
        # Check base situations are still there
        assert len(merged.situations) == len(default_template.situations) + 1

    def test_merge_partial_situation_override(self) -> None:
        """Test merging overlay that only overrides schema, inherits other fields."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
situations:
  save_node_output:
    schema: "{outputs}/different_schema.{file_extension}"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        merged = ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check schema was overridden
        assert merged.situations["save_node_output"].schema == "{outputs}/different_schema.{file_extension}"
        # Check policy was inherited from base
        base_policy = default_template.situations["save_node_output"].policy
        merged_policy = merged.situations["save_node_output"].policy
        assert merged_policy.on_collision == base_policy.on_collision
        assert merged_policy.create_dirs == base_policy.create_dirs

    def test_merge_override_directory(self) -> None:
        """Test merging overlay that overrides an existing directory."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
directories:
  outputs:
    path_schema: "my_custom_outputs"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        merged = ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check directory was overridden
        assert merged.directories["outputs"].path_schema == "my_custom_outputs"
        # Check other directories are inherited
        assert "inputs" in merged.directories

    def test_merge_add_new_directory(self) -> None:
        """Test merging overlay that adds a new directory."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
directories:
  custom_dir:
    path_schema: "path/to/custom"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        merged = ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check new directory was added
        assert "custom_dir" in merged.directories
        assert merged.directories["custom_dir"].path_schema == "path/to/custom"
        # Check base directories are still there
        assert len(merged.directories) == len(default_template.directories) + 1

    def test_merge_environment_variables(self) -> None:
        """Test merging environment variables."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
environment:
  NEW_VAR: "new_value"
  ANOTHER_VAR: "another_value"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        merged = ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check new env vars were added
        assert merged.environment["NEW_VAR"] == "new_value"
        assert merged.environment["ANOTHER_VAR"] == "another_value"


class TestOverrideTracking:
    """Tests for override tracking during merge."""

    def test_track_metadata_name_override(self) -> None:
        """Test that name override is always tracked as MODIFIED."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check name override was tracked
        name_overrides = [
            o for o in validation.overrides if o.category == ProjectOverrideCategory.METADATA and o.name == "name"
        ]
        assert len(name_overrides) == 1
        assert name_overrides[0].action == ProjectOverrideAction.MODIFIED

    def test_track_situation_modified(self) -> None:
        """Test that modifying existing situation is tracked as MODIFIED."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
situations:
  save_file:
    schema: "{outputs}/different.{file_extension}"
    policy:
      on_collision: "fail"
      create_dirs: false
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check situation override was tracked
        sit_overrides = [
            o for o in validation.overrides if o.category == ProjectOverrideCategory.SITUATION and o.name == "save_file"
        ]
        assert len(sit_overrides) == 1
        assert sit_overrides[0].action == ProjectOverrideAction.MODIFIED

    def test_track_situation_added(self) -> None:
        """Test that adding new situation is tracked as ADDED."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
situations:
  brand_new_situation:
    situation_template_schema_version: "0.1.0"
    schema: "{outputs}/new.{file_extension}"
    policy:
      on_collision: "create_new"
      create_dirs: true
    fallback: null
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check situation addition was tracked
        sit_overrides = [
            o
            for o in validation.overrides
            if o.category == ProjectOverrideCategory.SITUATION and o.name == "brand_new_situation"
        ]
        assert len(sit_overrides) == 1
        assert sit_overrides[0].action == ProjectOverrideAction.ADDED

    def test_track_directory_modified(self) -> None:
        """Test that modifying existing directory is tracked as MODIFIED."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
directories:
  inputs:
    path_schema: "custom_inputs"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check directory override was tracked
        dir_overrides = [
            o for o in validation.overrides if o.category == ProjectOverrideCategory.DIRECTORY and o.name == "inputs"
        ]
        assert len(dir_overrides) == 1
        assert dir_overrides[0].action == ProjectOverrideAction.MODIFIED

    def test_track_directory_added(self) -> None:
        """Test that adding new directory is tracked as ADDED."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
directories:
  new_directory:
    path_schema: "path/to/new"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check directory addition was tracked
        dir_overrides = [
            o
            for o in validation.overrides
            if o.category == ProjectOverrideCategory.DIRECTORY and o.name == "new_directory"
        ]
        assert len(dir_overrides) == 1
        assert dir_overrides[0].action == ProjectOverrideAction.ADDED

    def test_track_environment_modified(self) -> None:
        """Test that modifying existing env var is tracked as MODIFIED."""
        # First create a base with an env var
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
environment:
  EXISTING_VAR: "modified_value"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        # Create a base template with the env var
        base_with_env = ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="Base",
            situations=default_template.situations,
            directories=default_template.directories,
            environment={"EXISTING_VAR": "original_value"},
            description=None,
        )

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=base_with_env,
            overlay=overlay,
            validation_info=validation,
        )

        # Check env var override was tracked
        env_overrides = [
            o
            for o in validation.overrides
            if o.category == ProjectOverrideCategory.ENVIRONMENT and o.name == "EXISTING_VAR"
        ]
        assert len(env_overrides) == 1
        assert env_overrides[0].action == ProjectOverrideAction.MODIFIED

    def test_track_environment_added(self) -> None:
        """Test that adding new env var is tracked as ADDED."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
environment:
  NEW_VAR: "new_value"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check env var addition was tracked
        env_overrides = [
            o for o in validation.overrides if o.category == ProjectOverrideCategory.ENVIRONMENT and o.name == "NEW_VAR"
        ]
        assert len(env_overrides) == 1
        assert env_overrides[0].action == ProjectOverrideAction.ADDED

    def test_track_multiple_overrides(self) -> None:
        """Test tracking multiple overrides in a single merge."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
description: "Custom description"
situations:
  save_file:
    schema: "{custom}.{file_extension}"
    policy:
      on_collision: "overwrite"
      create_dirs: true
  new_situation:
    situation_template_schema_version: "0.1.0"
    schema: "{new}.{file_extension}"
    policy:
      on_collision: "create_new"
      create_dirs: true
    fallback: null
directories:
  outputs:
    path_schema: "custom_outputs"
  new_dir:
    path_schema: "new_directory"
environment:
  VAR1: "value1"
  VAR2: "value2"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Count overrides by category
        metadata_overrides = [o for o in validation.overrides if o.category == ProjectOverrideCategory.METADATA]
        situation_overrides = [o for o in validation.overrides if o.category == ProjectOverrideCategory.SITUATION]
        directory_overrides = [o for o in validation.overrides if o.category == ProjectOverrideCategory.DIRECTORY]
        env_overrides = [o for o in validation.overrides if o.category == ProjectOverrideCategory.ENVIRONMENT]

        assert len(metadata_overrides) == 2  # name + description  # noqa: PLR2004
        assert len(situation_overrides) == 2  # 1 modified + 1 added  # noqa: PLR2004
        assert len(directory_overrides) == 2  # 1 modified + 1 added  # noqa: PLR2004
        assert len(env_overrides) == 2  # 2 added  # noqa: PLR2004

        # Check actions
        assert any(o.action == ProjectOverrideAction.MODIFIED for o in situation_overrides)
        assert any(o.action == ProjectOverrideAction.ADDED for o in situation_overrides)


class TestValidationDuringMerge:
    """Tests for validation errors during merge."""

    def test_invalid_new_situation_schema(self) -> None:
        """Test that invalid schema in new situation causes validation error."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
situations:
  bad_situation:
    situation_template_schema_version: "0.1.0"
    schema: "{unclosed"
    policy:
      on_collision: "create_new"
      create_dirs: true
    fallback: null
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check validation error was recorded
        assert validation.status == ProjectValidationStatus.UNUSABLE
        assert any("schema" in p.field_path.lower() for p in validation.problems)

    def test_incomplete_policy_in_override(self) -> None:
        """Test that incomplete policy in situation override causes validation error."""
        yaml_text = """
project_template_schema_version: "0.1.0"
name: "Custom Project"
situations:
  save_file:
    policy:
      on_collision: "overwrite"
"""
        overlay_validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, overlay_validation)
        assert overlay is not None

        ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        default_template = _SYSTEM_DEFAULTS
        assert default_template is not None

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        ProjectTemplate.merge(
            base=default_template,
            overlay=overlay,
            validation_info=validation,
        )

        # Check validation error for incomplete policy
        assert validation.status == ProjectValidationStatus.UNUSABLE
        assert any("policy" in p.field_path and "both" in p.message.lower() for p in validation.problems)
