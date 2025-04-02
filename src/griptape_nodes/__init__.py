"""Griptape Nodes package."""

import argparse
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import get_key, load_dotenv, set_key
from rich.console import Console
from rich.prompt import Confirm, Prompt
from xdg_base_dirs import xdg_config_home

from griptape_nodes.api.app import main as api_main
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager

INSTALL_SCRIPT = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/install.sh"
CONFIG_DIR = xdg_config_home() / "griptape_nodes"
ENV_FILE = CONFIG_DIR / ".env"
CONFIG_FILE = CONFIG_DIR / "griptape_nodes_config.json"
REPO_NAME = "griptape-ai/griptape-nodes"

console = Console()


def main() -> None:
    load_dotenv(ENV_FILE)
    _init_config()
    _init_api_key()

    # Hack to make paths "just work". # noqa: FIX004
    # Without this, packages like `nodes` don't properly import.
    # Long term solution could be to make `nodes` a proper src-layout package
    # but current engine relies on importing files rather than packages.

    sys.path.append(str(Path.cwd()))

    args = _get_args()
    _process_args(args)


def _get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="griptape-nodes", description="Griptape Nodes Engine.")

    # The main command (engine|config|update|version)
    parser.add_argument(
        "command",
        help="Command to run",
        nargs="?",
        choices=["engine", "config", "update", "version"],
        default="engine",
    )

    # Optional second argument for config subcommand (e.g., config list)
    parser.add_argument(
        "config_subcommand",
        help="Subcommand for 'config'",
        nargs="?",
        choices=["list"],
        default=None,
    )
    return parser.parse_args()


def _init_config() -> None:
    """Initializes the config directory if it doesn't exist."""
    config_dir = xdg_config_home() / "griptape_nodes"
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)

    files_to_create = [
        (ENV_FILE, ""),
        (CONFIG_FILE, "{}"),
    ]

    for file_name in files_to_create:
        file_path = config_dir / file_name[0]
        if not file_path.exists():
            with Path.open(file_path, "w") as file:
                file.write(file_name[1])


def _init_api_key() -> None:
    """Prompts the user for their GT_CLOUD_API_KEY and stores it in config directory."""
    api_key = get_key(ENV_FILE, "GT_CLOUD_API_KEY")

    if not api_key:
        while not api_key:
            api_key = Prompt.ask(
                "Please enter your API key to continue",
                default=None,
                show_default=False,
            )
        set_key(ENV_FILE, "GT_CLOUD_API_KEY", api_key)


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
    """Automatically updates the script to the latest version using a shell command."""
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
    return ConfigManager().user_config


def _list_user_configs() -> list[Path]:
    """Lists the user configuration files.

    Returns:
        list[Path]: All config files.
    """
    return ConfigManager().config_files


def _process_args(args: argparse.Namespace) -> None:
    if args.command == "engine":
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
