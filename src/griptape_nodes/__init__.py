"""Griptape Nodes package."""

import argparse
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv, set_key
from dotenv.main import DotEnv
from rich.console import Console
from rich.prompt import Confirm, Prompt
from xdg_base_dirs import xdg_config_home

from griptape_nodes.api.app import main as api_main
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

INSTALL_SCRIPT = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/install.sh"
CONFIG_DIR = xdg_config_home() / "griptape_nodes"
ENV_FILE = CONFIG_DIR / ".env"
CONFIG_FILE = CONFIG_DIR / "griptape_nodes_config.json"
REPO_NAME = "griptape-ai/griptape-nodes"

console = Console()
config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)


def main() -> None:
    load_dotenv(ENV_FILE)

    # Hack to make paths "just work". # noqa: FIX004
    # Without this, packages like `nodes` don't properly import.
    # Long term solution could be to make `nodes` a proper src-layout package
    # but current engine relies on importing files rather than packages.
    sys.path.append(str(Path.cwd()))

    args = _get_args()
    _process_args(args)


def _run_init(api_key: str | None = None) -> None:
    """Runs through the engine init steps, optionally skipping prompts if the user provided `--api-key`."""
    _prompt_for_workspace()
    _prompt_for_api_key(api_key)

    console.print(
        "[bold green]Initialization complete! You can now run the engine with 'griptape-nodes' (or just 'gtn').[/bold green]"
    )


def _get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="griptape-nodes", description="Griptape Nodes Engine.")

    # The main command (engine|config|update|version|init)
    parser.add_argument(
        "command",
        help="Command to run",
        nargs="?",
        choices=["init", "engine", "config", "update", "version"],
        default="engine",
    )

    # Optional subcommand for 'config' (e.g., config list)
    parser.add_argument(
        "config_subcommand",
        help="Subcommand for 'config'",
        nargs="?",
        choices=["list"],
        default=None,
    )

    # Optionally allow setting the API key directly for the init command
    parser.add_argument("--api-key", help="Override the Griptape Nodes API key when running 'init'.", required=False)

    return parser.parse_args()


def _init_system_config() -> bool:
    """Initializes the system config directory if it doesn't exist.

    Returns:
        bool: True if the system config directory was created, False otherwise.

    """
    config_dir = xdg_config_home() / "griptape_nodes"
    is_first_init = False
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)
        is_first_init = True

    files_to_create = [
        (ENV_FILE, ""),
        (CONFIG_FILE, "{}"),
    ]

    for file_name in files_to_create:
        file_path = config_dir / file_name[0]
        if not file_path.exists():
            with Path.open(file_path, "w") as file:
                file.write(file_name[1])

    return is_first_init


def _prompt_for_api_key(api_key: str | None = None) -> None:
    """Prompts the user for their GT_CLOUD_API_KEY unless it's provided."""
    default_key = api_key or DotEnv(ENV_FILE, verbose=False).get("GT_CLOUD_API_KEY")
    current_key = Prompt.ask(
        "Please enter your Griptape Nodes API key",
        default=default_key,
        show_default=True,
    )
    if current_key is None:
        console.print("[bold red]API key cannot be empty![/bold red]")
        sys.exit(1)

    set_key(ENV_FILE, "GT_CLOUD_API_KEY", current_key)
    config_manager.set_config_value("nodes.Griptape.GT_CLOUD_API_KEY", "$GT_CLOUD_API_KEY")
    secrets_manager.set_secret("GT_CLOUD_API_KEY", current_key)


def _prompt_for_workspace() -> None:
    """Prompts the user for their workspace directory and stores it in config directory."""
    workspace_directory = config_manager.get_config_value("workspace_directory")

    workspace_directory = Prompt.ask(
        "Please enter your workspace directory",
        default=workspace_directory,
        show_default=True,
    )
    config_manager.workspace_path = str(Path(workspace_directory).expanduser().resolve())
    console.print(f"[bold green]Workspace directory set to: {config_manager.workspace_path}[/bold green]")


def _get_latest_version(repo: str) -> str:
    """Fetches the latest release tag from a GitHub repository using httpx.

    Args:
        repo (str): Repository name in the format "owner/repo"

    Returns:
        str: Latest release tag (e.g., "v0.31.4")
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()["tag_name"]


def _auto_update() -> None:
    """Automatically updates the script to the latest version if the user confirms."""
    current_version = _get_current_version()
    latest_version = _get_latest_version(REPO_NAME)

    if current_version < latest_version:
        update = Confirm.ask(
            f"Your current engine version, {current_version}, is behind the latest release, {latest_version}. Update now?",
        )

        if update:
            _install_latest_release()


def _install_latest_release() -> None:
    """Installs the latest release of the script using a shell command."""
    with console.status("[bold green]Updating...", spinner="dots"):
        curl_process = subprocess.run(  # noqa: S603
            ["curl", "-LsSf", INSTALL_SCRIPT],  # noqa: S607
            capture_output=True,
            check=False,
            text=True,
        )
        subprocess.run(  # noqa: S603
            ["bash"],  # noqa: S607
            input=curl_process.stdout,
            capture_output=True,
            check=True,
            text=True,
        )
    console.print(
        "[bold green]Update complete! Restart the engine by running 'griptape-nodes' (or just 'gtn').[/bold green]"
    )
    sys.exit(0)


def _get_current_version() -> str:
    """Fetches the current version of the script.

    Returns:
        str: Current version (e.g., "v0.31.4")
    """
    return f"v{importlib.metadata.version('griptape_nodes')}"


def _get_user_config() -> dict:
    """Fetches the user configuration from the config file.

    Returns:
        dict: User configuration.
    """
    return config_manager.user_config


def _list_user_configs() -> list[Path]:
    """Lists the user configuration files.

    Returns:
        list[Path]: All config files.
    """
    return config_manager.config_files


def _process_args(args: argparse.Namespace) -> None:
    is_first_init = _init_system_config()

    if args.command == "init":
        _run_init(api_key=args.api_key)
    elif args.command == "engine":
        if is_first_init:
            # Default init flow if it's truly the first time
            _run_init()

        _auto_update()
        api_main()
    elif args.command == "config":
        if args.config_subcommand == "list":
            for config in _list_user_configs():
                console.print(f"[bold green]{config}[/bold green]")
        else:
            sys.stdout.write(json.dumps(_get_user_config(), indent=2))
    elif args.command == "update":
        _install_latest_release()
    elif args.command == "version":
        version = _get_current_version()
        console.print(f"[bold green]{version}[/bold green]")
    else:
        msg = f"Unknown command: {args.command}"
        raise ValueError(msg)


if __name__ == "__main__":
    main()
