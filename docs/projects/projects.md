# Projects

A project template is a configuration that defines how files are organized and saved. It is the combination of [situations](situations.md), [directories](directories.md), and [environment variables](environment.md) that every node consults when it needs to save a file.

By default, Griptape Nodes ships with a built-in project template that handles the common cases — saving images, audio, and other outputs to an `outputs` folder in your workspace. A project file lets you change any of that: redirect where a particular kind of file is saved, add a new named location (like `renders/4k`), or inject environment variables specific to your project. You only write down the things you want to change; everything else continues to use the [default situations](situations.md#default-situations) and [default directories](directories.md#default-directories).

## The project file

Your workspace-level customizations live in a file named:

```
griptape-nodes-project.yml
```

Place this file in your workspace directory. It is optional — if absent, the [system defaults](#the-system-defaults) apply.

## Project file structure

```yaml
project_template_schema_version: "0.1.0"
name: "My Project"
description: "Optional description"

directories:
  outputs:
    path_macro: "renders"       # override the outputs directory path
  renders_4k:                   # add a new directory
    path_macro: "renders/4k"

situations:
  save_node_output:             # override an existing situation
    macro: "{outputs}/{workflow_name?:_}{file_name_base}{_index?:03}.{file_extension}"
  archive_render:               # add a new situation
    macro: "{renders_4k}/{workflow_name?:_}{file_name_base}.{file_extension}"
    policy:
      on_collision: overwrite
      create_dirs: true

environment:
  PROJECT_CODENAME: "aurora"

file_extension_directories:
  png: "images"
  mp4: "{outputs}/videos"
```

### Fields reference

| Field                             | Required | Description                                                                                  |
| --------------------------------- | -------- | -------------------------------------------------------------------------------------------- |
| `project_template_schema_version` | Yes      | Must match the supported version (`"0.3.0"`)                                                 |
| `name`                            | Yes      | Human-readable name for this project                                                         |
| `description`                     | No       | Optional description                                                                         |
| `situations`                      | No       | Dict of situation overrides and additions                                                    |
| `directories`                     | No       | Dict of directory overrides and additions                                                    |
| `environment`                     | No       | Dict of custom key-value variables                                                           |
| `file_extension_directories`      | No       | Extension-to-folder routing; see [File Extension Directories](file_extension_directories.md) |

### Situation fields

Each entry under `situations` is keyed by situation name. You can provide any subset of these fields:

| Field                 | Required for new | Description                                        |
| --------------------- | ---------------- | -------------------------------------------------- |
| `macro`               | Yes              | Macro template string for the file path            |
| `policy`              | Yes              | Must include both `on_collision` and `create_dirs` |
| `policy.on_collision` | Yes              | One of: `create_new`, `overwrite`, `fail`          |
| `policy.create_dirs`  | Yes              | `true` to create missing directories automatically |
| `fallback`            | No               | Name of another situation to use if this one fails |
| `description`         | No               | Human-readable description                         |

When *modifying* an existing situation, you only need to provide the fields you want to change. When *adding* a new situation, `macro` and `policy` are required.

### Directory fields

Each entry under `directories` is keyed by the logical name:

| Field        | Required for new | Description                                                        |
| ------------ | ---------------- | ------------------------------------------------------------------ |
| `path_macro` | Yes              | Path string, may contain macros or environment variable references |

## The merge model

The project system uses a two-layer model:

1. **System defaults** — a complete, built-in project template that ships with Griptape Nodes. It defines all default situations and directories and is always loaded first.

1. **Workspace overlay** — the contents of `griptape-nodes-project.yml`, if present. This file is merged *on top of* the system defaults.

The merge behavior is additive and field-level:

- Situations and directories from the overlay are merged into the defaults. An overlay situation with the same name as a default situation changes only the fields you specify (e.g., just the macro, or just the policy). An overlay situation with a new name is added alongside the defaults.
- Environment entries in the overlay override entries with the same key in the defaults. New keys are added.
- `file_extension_directories` entries merge per-key the same way as environment entries. A `null` value tombstones the base entry.
- The `name` field is always taken from the overlay (required).

You never need to repeat default values. Your project file only needs to contain the things you want to change.

## Validation status

When a project file is loaded, it receives one of four statuses:

| Status     | Meaning                                                                |
| ---------- | ---------------------------------------------------------------------- |
| `GOOD`     | Loaded and fully valid                                                 |
| `FLAWED`   | Loaded but has warnings (e.g., schema version mismatch) — still usable |
| `UNUSABLE` | Errors prevent the template from being used                            |
| `MISSING`  | The project file was not found                                         |

When a project file has `UNUSABLE` or `MISSING` status, Griptape Nodes falls back to the system defaults. You can inspect validation problems (with field paths and line numbers) to diagnose issues.

## The system defaults

The system defaults define these situations and directories out of the box. See [Situations](situations.md) and [Directories](directories.md) for full details.
