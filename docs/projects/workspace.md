# Workspace

The workspace is the root directory for all your work in Griptape Nodes. It is the starting point from which relative file paths are resolved.

## Configuring the workspace

The workspace directory is set via the `workspace_directory` key in your settings. By default, this is a folder in your home directory, but you can point it anywhere on disk. See [Engine Configuration](../configuration.md#workspace-directory) for details on how to change this setting.

## How paths resolve

All relative paths in the project system are resolved against the **project base directory**. When a project file (`griptape-nodes-project.yml`) is present, the project base directory is the folder containing that file — which is normally the workspace root. When no project file is present, the workspace directory itself is used as the base.

For example, if your workspace is `/Users/you/my_project/` and a situation macro resolves to `outputs/render_001.png`, the final absolute path is `/Users/you/my_project/outputs/render_001.png`.

## Workspace and the project file

When Griptape Nodes starts, it looks for a file named `griptape-nodes-project.yml` in your workspace directory. If it finds one, it merges the contents of that file on top of the system defaults to produce the active project template. If no file is found, the system defaults are used as-is.

See [Projects](projects.md) for the full details on the project file and merge model.

## Summary

| Setting                      | Description                                              |
| ---------------------------- | -------------------------------------------------------- |
| `workspace_directory`        | The root directory for your work                         |
| `griptape-nodes-project.yml` | Optional file in the workspace for project customization |

All relative paths in macros and directory definitions resolve against the project base directory, which is the folder containing the project file (or the workspace directory when no project file exists).
