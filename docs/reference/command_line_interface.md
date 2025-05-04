# Griptape Nodes Command Line Documentation

This page describes what can be done in the terminal (or PowerShell) regarding the `griptape-nodes` (or `gtn`) command. For those who may be new to command-line interfaces (CLIs), a CLI is a text-based way to interact with software by typing commands instead of clicking buttons in a UI.

`griptape-nodes` (or its shorthand alias `gtn`) is a command-line tool specifically designed to launch, update, and manage the Griptape Nodes Engine installation on your computer. This tool handles tasks like initializing your workspace, updating the software, managing configuration settings, and starting the engine that powers the web-based Griptape Nodes editor. The actual creation and editing of workflows happens in the web interface that opens when you run the engine.

## Basic Usage

```
griptape-nodes [options] [COMMAND]
```

If no command is specified, the tool defaults to the `engine` command.

## Global Options

- `--no-update` - Skip the automatic update check when starting the engine

## Commands

### `engine` (Default Command)

Run the Griptape Nodes engine.

```
griptape-nodes engine
```

This will start the Griptape Nodes engine and open the web interface at https://nodes.griptape.ai.

### `init`

Initialize a new workspace for Griptape Nodes.

```
griptape-nodes init [options]
```

Options:

- `--api-key` - Directly specify your Griptape API key without being prompted
- `--workspace-directory` - Directly specify your workspace directory without being prompted

### `config`

Manage your Griptape Nodes configuration.

```
griptape-nodes config SUBCOMMAND
```

Subcommands:

- `show` - Show the current configuration settings
- `list` - List all configuration files in order of precedence
- `reset` - Reset your configuration to default values

### `self`

Manage the CLI installation itself.

```
griptape-nodes self SUBCOMMAND
```

Subcommands:

- `update` - Update the CLI to the latest version
- `uninstall` - Uninstall the CLI, removing configuration and data directories
- `version` - Display the current version of the CLI

### `assets`

Manage local assets (libraries, workflows, etc.).

```
griptape-nodes assets SUBCOMMAND
```

Subcommands:

- `update` - Update bundled assets to the latest version

## Configuration

Griptape Nodes stores its configuration in the following locations:

- Configuration directory: `~/.config/griptape_nodes` (Linux/macOS) or `%APPDATA%\griptape_nodes` (Windows)
- Data directory: `~/.local/share/griptape_nodes` (Linux/macOS) or `%LOCALAPPDATA%\griptape_nodes` (Windows)
- Configuration file: `griptape_nodes_config.json` in the configuration directory
- Environment file: `.env` in the configuration directory

## Workflow

Typical usage flow:

1. Run `griptape-nodes init` to set up your workspace and API key
1. Run `griptape-nodes` to start the engine
1. Use the web interface to create and manage your workflows
1. Update when needed with `griptape-nodes self update`
