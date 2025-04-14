# Engine Configuration

When running Griptape Nodes engine on your own machine, you are provided with utilities to manage configuration settings. Understanding how the configuration settings are loaded is important as you build out and manage more complicated projects or share projects with your team members.

> During installation, `gtn init` was run automatically.

## Configuration Loading

Griptape Nodes employs a specific search order to load settings from environment variables and configuration files. Understanding this process is key to managing your setup.

1. **Environment Variables (`.env`)**
    Environment variables are used to securely store sensitive secrets like API keys. Griptape Nodes automatically loads env files, making these secrets available to the application.

    - The primary `.env` file is loaded from the system-wide user configuration directory: `xdg_config_home() / "griptape_nodes" / ".env"` (commonly `~/.config/griptape_nodes/.env`).
    - This file is intended for secrets like `GT_CLOUD_API_KEY`, `OPENAI_API_KEY`.

    > You shouldn't interact with these files directly. Griptape Nodes manages your environment variables through its Settings dialog.

1. **Configuration Files (`griptape_nodes_config.[json|yaml|toml]`)**
    Configuration files hold information important for Griptape Nodes operation, such as where to locate Node Libraries, as well as user preferences to customize the Griptape Nodes experience.

    - If no configuration files are found, Griptape Nodes will issue a warning and attempt to run using built-in default values.
    - The application searches for configuration files named `griptape_nodes_config` with `.json`, `.yaml`, or `.toml` extensions.
    - It searches in multiple locations in a specific order. **All** valid configuration files found across these locations are loaded and their settings are **merged**.
    - **Search Order (Lower numbers are checked first, but higher numbers override):**
        1. **System-wide Shared:** Paths in `XDG_CONFIG_DIRS` (e.g., `/etc/xdg/griptape_nodes/`). Settings here have the *lowest* priority.
        1. **System-wide User:** Path in `XDG_CONFIG_HOME` (e.g., `~/.config/griptape_nodes/`). Settings here override System-wide Shared.
        1. **Implicit CWD Subdirectory:** `current_working_directory / "GriptapeNodes" /` (relative to where `gtn` is run). Settings here override System User.
        1. **Current Directory & Parents:** The current working directory (`cwd`) and its parent directories up to the user's home directory (`~`). Settings found closer to `cwd` have *higher* priority and override settings from parent directories and all locations above.
    - **Override Priority:** Because settings are merged, if the same setting exists in multiple files, the value from the file found *later* in the search order (i.e., closer to the current directory) takes precedence. For example, a setting in `./griptape_nodes_config.json` will override the same setting in `~/.config/griptape_nodes/griptape_nodes_config.json`.
    - **File Type Priority:** If multiple file types (e.g., `.json` and `.yaml`) exist in the *same directory*, they are all loaded, but the priority for merging within that *single* directory is: `.json` > `.yaml` > `.toml`.

1. **Defaults and Merging**
    Griptape Nodes comes with built-in default settings for various options, including the default workspace directory. These defaults are used unless overridden by settings loaded from discovered configuration files.

    - Settings loaded from the first found configuration file override the built-in default values.
    - If no configuration file is found in any of the search paths, the application uses only the built-in defaults.
    - One key default is `workspace_directory`, which defaults to `<current_working_directory>/GriptapeNodes` if not specified in a loaded configuration file.

1. **Runtime Management (`ConfigManager`)**
    After initial settings are loaded, the `ConfigManager` handles runtime operations using the final resolved configuration, particularly the workspace directory. It's responsible for saving user-specific changes, like registered workflows, back to a configuration file within the workspace.

    - Once settings are loaded, the `ConfigManager` uses the final resolved `workspace_directory`.
    - Modifications made at runtime (e.g., registering custom workflows) are typically saved by the `ConfigManager` into a `griptape_nodes_config.json` file located within this resolved `workspace_directory`.

## Loading Examples

Here are a few scenarios to illustrate how configuration files are located and loaded:

**Scenario 1: Using Defaults**

- You run `gtn init` and accept the default settings.

- `gtn init` creates `~/.config/griptape_nodes/griptape_nodes_config.json` and `~/.config/griptape_nodes/.env`. It sets `workspace_directory` inside the `.json` file to point to `<current_directory_where_init_was_run>/GriptapeNodes`.

- You later run `gtn` from `/home/user/my_project/`.

- **File Structure:**

    ```
    /home/user/
        my_project/          <-- CWD when running 'gtn'
            GriptapeNodes/   <-- Default Workspace (may contain runtime saved config)
            my_flow.graph.json
        .config/
            griptape_nodes/
                .env                     # Loaded for environment variables
                griptape_nodes_config.json # Contains workspace_directory = /home/user/my_project/GriptapeNodes
    ```

- **Loading Process:**

    1. Checks `/etc/xdg/griptape_nodes/` (Assume not found).
    1. Checks `~/.config/griptape_nodes/griptape_nodes_config.json` (Found!).
    1. **Result:** The application loads settings from `~/.config/griptape_nodes/griptape_nodes_config.json`. The `workspace_directory` is set to `/home/user/my_project/GriptapeNodes`. Subsequent runtime changes managed by `ConfigManager` will be saved to `/home/user/my_project/GriptapeNodes/griptape_nodes_config.json`.

**Scenario 2: Custom Workspace**

- You run `gtn init --workspace-directory /data/gtn_work`.

- `gtn init` creates `~/.config/griptape_nodes/griptape_nodes_config.json` (setting `workspace_directory = "/data/gtn_work"`) and `~/.config/griptape_nodes/.env`.

- You might manually create `/data/gtn_work/griptape_nodes_config.yaml` to store project-specific settings.

- You run `gtn` from `/home/user/some_dir/`.

- **File Structure:**

    ```
    /home/user/
        some_dir/            <-- CWD when running 'gtn'
        .config/
            griptape_nodes/
                .env                     # Loaded for environment variables
                griptape_nodes_config.json # Contains workspace_directory = /data/gtn_work
    /data/
        gtn_work/            <-- Custom Workspace
            griptape_nodes_config.yaml # Manually created / runtime saved config
            project_flows/
    ```

- **Loading Process:**

    1. Checks `/etc/xdg/griptape_nodes/` (Assume not found).
    1. Checks `~/.config/griptape_nodes/griptape_nodes_config.json` (Found!).
    1. **Result:** The application *initially* loads settings from `~/.config/griptape_nodes/griptape_nodes_config.json`. The `workspace_directory` is set to `/data/gtn_work`. Even though `/data/gtn_work/griptape_nodes_config.yaml` exists, it's not checked during initial load because a higher priority file was found. Runtime changes will be saved back to `/data/gtn_work/griptape_nodes_config.json` (overwriting/merging with the YAML potentially, depending on `ConfigManager`'s save logic).

**Scenario 3: Config in Current Directory (No System Config)**

- You haven't run `gtn init`, or you deleted `~/.config/griptape_nodes/`.

- You create a project-specific config file directly in your project folder.

- You run `gtn` from `/home/user/my_project/`.

- **File Structure:**

    ```
    /home/user/
        my_project/          <-- CWD when running 'gtn'
            griptape_nodes_config.toml # User-created config
            GriptapeNodes/   <-- Potential default workspace location
            my_flow.graph.json
    ```

- **Loading Process:**

    1. Checks `/etc/xdg/griptape_nodes/` (Assume not found).
    1. Checks `~/.config/griptape_nodes/` (Assume not found).
    1. Checks `/home/user/my_project/GriptapeNodes/` (Assume not found).
    1. Checks `/home/user/my_project/griptape_nodes_config.toml` (Found!).
    1. **Result:** The application loads settings from `/home/user/my_project/griptape_nodes_config.toml`. If this file specifies a `workspace_directory`, that path is used. If not, the default (`<cwd>/GriptapeNodes` = `/home/user/my_project/GriptapeNodes`) is used.

## Workspace Directory

During `gtn init`, you specify a Workspace Directory. This is the root for your projects, saved flows, and potentially project-specific settings.

While `gtn init` might suggest `<current_working_directory>/GriptapeNodes` as a default, you can choose any location. Griptape Nodes uses the exact path you provide, which is then stored in the system `griptape_nodes_config.json`.

It does **not** automatically search within a hardcoded `GriptapeNodes` subdirectory; it relies solely on the configured path.
