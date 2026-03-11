# Workspace

The workspace is the root directory where a project's files live — inputs, outputs, temp files, and previews all land here by default.

## How workspace and project relate

A project file (`griptape-nodes-project.yml`) defines a project. By default, the workspace for that project is the directory containing the project file. The two concepts are the same in the common case, but can be decoupled when needed.

- **`{project_dir}`** — always the directory containing the project file. Read-only; you cannot change it.
- **`{workspace_dir}`** — the root for file outputs. Defaults to `{project_dir}`, but can be redirected in the project file.

## Configuring the workspace root (engine default)

The `workspace_directory` setting in your engine config controls where new projects are created and where the engine looks for a project file on startup. By default this is a folder in your home directory. See [Engine Configuration](../configuration.md#workspace-directory) for details.

## Overriding workspace_dir per project

If you want a project's files to land somewhere other than the project file's directory, set `workspace_dir` in your project file:

```yaml
project_template_schema_version: "0.1.0"
name: "My Project"
workspace_dir: "/data/renders"   # absolute path
# workspace_dir: "~/renders"     # ~ is expanded to your home directory
# workspace_dir: "../outputs"    # relative paths resolve against the project file's directory
```

With this set, `{workspace_dir}` resolves to the configured path and all default directories (`outputs`, `inputs`, `temp`, `previews`) follow it there.

## How paths resolve

All relative paths in directory definitions are resolved against the workspace directory. When `workspace_dir` is not set in the project file, this is the folder containing the project file. When no project file is present, the engine's `workspace_directory` config value is used.

## Summary

| Concept                         | Description                                                                 |
| ------------------------------- | --------------------------------------------------------------------------- |
| `workspace_directory` config    | Engine default: where to create projects and look for a project file        |
| `{project_dir}`                 | Directory containing the active project file (read-only)                    |
| `{workspace_dir}`               | Root for file outputs; defaults to `{project_dir}`, overridable per project |
| `workspace_dir` in project file | Optional override to point file outputs at a different directory            |
