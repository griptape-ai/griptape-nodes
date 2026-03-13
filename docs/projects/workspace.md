# Workspace

The workspace is the root directory for all your work within a project. It is the starting point from which relative file paths are resolved.

## Configuring the workspace

The workspace directory is set via the `workspace_directory` key in your settings. By default, this is a folder in your home directory, but you can point it anywhere on disk. See [Engine Configuration](../configuration.md#workspace-directory) for details on how to change this setting.

### Per-project workspace (project-adjacent config)

Each project directory can contain an optional `griptape_nodes_config.json` file **next to** the `griptape-nodes-project.yml`. When a project is loaded, this file is read and merged on top of the user config, letting you set a project-specific workspace directory without modifying your global settings.

```
/path/to/project/
  griptape-nodes-project.yml
  griptape_nodes_config.json   ← optional: {"workspace_directory": "/path/to/workspace"}
```

### Config resolution order

`workspace_directory` is resolved in this order (later entries win):

1. Built-in default
1. User config (`~/.config/griptape_nodes/griptape_nodes_config.json`)
1. Project-adjacent config (`<project_dir>/griptape_nodes_config.json`)
1. Environment variable (`GTN_CONFIG_WORKSPACE_DIRECTORY`)

This means a studio can distribute a `griptape_nodes_config.json` next to the project file to mandate a shared workspace. Because the project-adjacent config has higher priority than the user config, artists cannot override it through their personal settings — only an environment variable (set by the studio's launch environment) can take precedence.

## Example scenarios

### Scenario 1: Studio-mandated workspace

A studio stores projects on a shared NAS. The project directory includes a `griptape_nodes_config.json` that points all artists to the same shared workspace, so output files land in a predictable location regardless of where each artist's machine mounts the drive.

```
\\NAS\Projects\ProjectA\
  griptape-nodes-project.yml
  griptape_nodes_config.json
```

`griptape_nodes_config.json`:

```json
{
  "workspace_directory": "\\\\NAS\\Workspaces\\ProjectA"
}
```

When any artist loads this project, their workspace is automatically set to `\\NAS\Workspaces\ProjectA`.

### Scenario 2: Studio-controlled per-machine override

A studio wants most artists to use the shared NAS workspace from Scenario 1, but render farm machines should redirect output to local fast storage. The studio's launcher sets an environment variable before starting Griptape Nodes:

```
GTN_CONFIG_WORKSPACE_DIRECTORY=D:\LocalRenderCache\ProjectA
```

Because environment variables have the highest priority, this overrides both the user config and the project-adjacent config. The project files and YAML remain unchanged — only the launch environment differs per machine.

### Scenario 3: No project file

When there is no `griptape-nodes-project.yml`, there is also no project directory and therefore no project-adjacent config. The active workspace comes from whichever of the following is set (in priority order):

1. `GTN_CONFIG_WORKSPACE_DIRECTORY` environment variable
1. `workspace_directory` in `~/.config/griptape_nodes/griptape_nodes_config.json`
1. The built-in default (`~/griptape-nodes` in your home directory)

## How paths resolve

All relative paths in the project system are resolved against the **workspace directory**. If your workspace is `/Users/you/workspace/` and a situation macro resolves to `outputs/render_001.png`, the final absolute path is `/Users/you/workspace/outputs/render_001.png`.

The **project base directory** (the folder containing `griptape-nodes-project.yml`) is exposed as the `{project_dir}` builtin variable but is not used as the resolution base for relative paths. It is used as a fallback when the path manager maps an absolute path back to a macro form and the path falls inside the project folder but outside any named directory.

## Workspace and the project file

When Griptape Nodes starts, it looks for a file named `griptape-nodes-project.yml` in your workspace directory. If it finds one, it merges the contents of that file on top of the system defaults to produce the active project template. If no file is found, the system defaults are used as-is.

See [Projects](projects.md) for the full details on the project file and merge model.

## Summary

| Setting                      | Description                                                       |
| ---------------------------- | ----------------------------------------------------------------- |
| `workspace_directory`        | The root directory for your work                                  |
| `griptape-nodes-project.yml` | Optional file in the project directory for template customization |
| `griptape_nodes_config.json` | Optional project-adjacent config to set a per-project workspace   |

All relative paths in macros and directory definitions resolve against the workspace directory.
