# Workspace

The workspace is the root directory for all your work within a project. It is the starting point from which relative file paths are resolved.

## How the workspace is determined

The workspace is resolved in this order:

1. **`workspace_directory` field in the project file** — if your `griptape-nodes-project.yml` contains a `workspace_directory` field, that path is used as the workspace. Absolute paths are used as-is; relative paths are resolved relative to the project file's directory. Tilde (`~`) and environment variables are expanded.

1. **Project file's directory** — if the project file does not include a `workspace_directory` field, the workspace defaults to the directory containing `griptape-nodes-project.yml`.

1. **`workspace_directory` setting** — if no project file is present (system defaults only), the workspace falls back to the `workspace_directory` key in your engine settings. See [Engine Configuration](../configuration.md#workspace-directory) for details.

## Configuring workspace in the project file

You can pin the workspace to a specific directory by adding a `workspace_directory` field to your project file:

```yaml
project_template_schema_version: "0.1.0"
name: "My Project"
workspace_directory: ~/my-project-files
```

Or relative to the project file's own location:

```yaml
project_template_schema_version: "0.1.0"
name: "My Project"
workspace_directory: ./outputs-root
```

When `workspace_directory` is omitted, the workspace is the folder containing the project file.

## How paths resolve

All relative paths in the project system are resolved against the workspace. For example, if the workspace is `/Users/you/my_project/` and a situation macro resolves to `outputs/render_001.png`, the final absolute path is `/Users/you/my_project/outputs/render_001.png`.

## Workspace and the project file

When Griptape Nodes starts, it looks for a file named `griptape-nodes-project.yml` in your workspace directory. If it finds one, it merges the contents of that file on top of the system defaults to produce the active project template. If no file is found, the system defaults are used as-is.

See [Projects](projects.md) for the full details on the project file and merge model.

## Summary

| Source                                | Description                                                     |
| ------------------------------------- | --------------------------------------------------------------- |
| `workspace_directory` in project file | Explicit path override; takes precedence over all other sources |
| Project file's directory              | Default when no `workspace_directory` field is set              |
| `workspace_directory` setting         | Fallback when no project file is present                        |

All relative paths in macros and directory definitions resolve against the workspace.
