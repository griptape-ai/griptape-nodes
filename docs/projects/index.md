# Project

The project system controls how files are organized, named, and saved when you work in Griptape Nodes. Every time a node saves an image, copies an uploaded file, or downloads a URL, the project system decides where that file goes and what it's called.

## Why it exists

Without a project system, every file save operation would require a hard-coded path. The project system replaces hard-coded paths with named templates called **macros** and named file-saving scenarios called **situations**. This lets you customize your entire project's file layout in one place, and every node that saves files automatically follows that layout.

## How the pieces fit together

```
workspace/                         ← workspace directory (your root)
  griptape-nodes-project.yml       ← optional: your customizations
  my_workflow/                     ← workflow directory
    inputs/                        ← default inputs directory
    outputs/                       ← default outputs directory
    temp/                          ← default temp directory
    .griptape-nodes-previews/      ← default previews directory
```

The conceptual hierarchy is:

```
workspace
  └── project template
        ├── situations    (where and how to save files in each scenario)
        ├── directories   (logical name → relative path mappings)
        └── environment   (custom key-value variables)
```

**Workspace** is the root directory for all your work. It is configured in your settings.

**Project template** is the configuration loaded at startup — first the system defaults, then any overrides you've placed in `griptape-nodes-project.yml` inside your workspace.

**Situations** are named file-saving scenarios. Each has a macro template that determines the file path and a policy that determines what happens when a file already exists.

**Directories** are logical name-to-path mappings. The name `outputs` means whatever path `outputs` is configured to. Directory names can be used as variables in macros.

**Environment** is a bag of custom key-value pairs that can be referenced in macros.

**Macros** are the template strings used in situations and directories to generate concrete file paths.

## Pages in this section

- [Workspace](workspace.md) — the root working context and how relative paths resolve
- [Projects](projects.md) — the project file format and the merge model
- [Macros](macros.md) — template syntax reference for generating file paths
- [Directories](directories.md) — logical name-to-path mappings
- [Situations](situations.md) — named file-saving scenarios with policies
- [Environment & Builtin Variables](environment.md) — custom variables and system-provided values
- [Customization Guide](customization.md) — practical examples for common customizations
