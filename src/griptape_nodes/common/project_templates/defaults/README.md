# System Default Project Template

This directory contains the system default project template used when no `project.yml` exists in a project.

## Files

- `project_template.yml` - Complete default project configuration with all situations

## Validation

The default template is loaded and validated at module import time. If validation fails, the system will raise a RuntimeError with details about what's broken.

This ensures:

- Default template is always valid
- Typos/errors are caught immediately in CI/tests
- Users can rely on defaults being correct

## Modifying Defaults

When modifying `project_template.yml`:

1. Ensure all syntax is correct (YAML, macro templates, etc.)
1. Run tests to validate changes
1. Update version numbers if making breaking changes
1. Update comments to keep documentation in sync

## Usage

Users can copy this file to their project root as `project.yml` and customize it:

```bash
cp defaults/project_template.yml /path/to/project/project.yml
```

The system will automatically use the project-specific version instead of these defaults.
