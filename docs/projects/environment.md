# Environment & Builtin Variables

## Environment

The `environment` section of a project file holds custom key-value pairs. These values are available for use in macros and directory `path_macro` fields.

```yaml
environment:
  RENDER_STYLE: "realistic"
  CLIENT_CODE: "ACME"
```

### Overlay behavior

Environment entries from your project file are merged on top of the system defaults. If a key exists in the defaults, your value replaces it. New keys are added.

### Referencing environment variables in macros

Values in the `environment` section can reference operating-system environment variables using `$` prefix:

```yaml
environment:
  OUTPUT_ROOT: "$RENDER_FARM_SHARE"
```

When `OUTPUT_ROOT` is used in a macro, the system first substitutes the environment variable `$RENDER_FARM_SHARE` from the operating system environment, then uses the result.

You can also use `$`-prefixed references directly in `path_macro` fields:

```yaml
directories:
  outputs:
    path_macro: "$SHARED_DRIVE/outputs"
```

## Builtin variables

Builtin variables are automatically available in all macros. You do not define them — the system provides their values at runtime. They cannot be overridden.

| Variable           | Type      | Description                                                                                                                                                                                                              |
| ------------------ | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `project_dir`      | directory | Absolute path to the folder of the active project (the folder containing `griptape-nodes-project.yml`)                                                                                                                   |
| `workspace_dir`    | directory | Absolute path to the working directory of the project — where all project directories are relative to (defaults to the project file's folder, or set explicitly via the `workspace_directory` field in the project file) |
| `workflow_name`    | string    | Name of the currently running workflow                                                                                                                                                                                   |
| `workflow_dir`     | directory | Absolute path to the directory containing the current workflow file                                                                                                                                                      |
| `static_files_dir` | string    | Name of the static files subdirectory (from settings, defaults to `staticfiles`)                                                                                                                                         |

### How builtins are resolved

Builtins are resolved at the moment a macro is evaluated — not when the project file is loaded. This means:

- `workflow_name` and `workflow_dir` reflect whichever workflow is currently executing
- `project_dir` reflects the folder containing the project file; `workspace_dir` reflects the project's working directory — these are the same unless `workspace_directory` is explicitly set in the project file (see [Workspace](workspace.md))

If a builtin variable is required but cannot be resolved (for example, `workflow_name` when no workflow is running), macro resolution fails with an error. If the variable is optional (marked with `?`), the block is silently omitted instead.

### Builtin variables in situation macros

The `save_static_file` situation uses `workflow_dir` and `static_files_dir`:

```
{workflow_dir?:/}{static_files_dir}/{file_name_base}.{file_extension}
```

If `workflow_dir` is available, the static files go into a subdirectory of the workflow folder. If not (the workflow hasn't been saved yet), the `{workflow_dir?:/}` block is omitted.

## Variable priority

When a macro is resolved, variables are supplied from these sources in priority order:

1. **Builtin variables** — always win; cannot be overridden by any other source
1. **Directory names** — resolved from the project's directory definitions; cannot be overridden by caller-supplied variables
1. **Caller-supplied variables** — values passed by the node or operation requesting path resolution

If a caller tries to supply a value for a builtin or directory name that differs from the system value, the resolution fails with a `DIRECTORY_OVERRIDE_ATTEMPTED` error.
