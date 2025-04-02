"""Griptape Nodes package."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from dotenv import get_key, set_key
from rich.prompt import Prompt
from xdg_base_dirs import xdg_config_home

from griptape_nodes.api.app import main as api_main
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager

INSTALL_SCRIPT = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/install.sh"
CONFIG_DIR = xdg_config_home() / "griptape_nodes"
ENV_FILE = CONFIG_DIR / ".env"
CONFIG_FILE = CONFIG_DIR / "griptape_nodes_config.json"


def main() -> None:
    # Hack to make paths "just work". # noqa: FIX004
    # Without this, packages like `nodes` don't properly import.
    # Long term solution could be to make `nodes` a proper src-layout package
    # but current engine relies on importing files rather than packages.
    _init_config()
    _init_api_key()
    sys.path.append(str(Path.cwd()))

    args = _get_args()
    _process_args(args)


def _get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="griptape-nodes", description="Griptape Nodes Engine.")
    parser.add_argument(
        "command", help="Command to run", nargs="?", choices=["engine", "config", "update"], default="engine"
    )
    return parser.parse_args()


def _init_config() -> None:
    """Initializes the config directory if it doesn't exist."""
    config_dir = xdg_config_home() / "griptape_nodes"
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)

    files_to_create = [
        ENV_FILE,
        CONFIG_FILE,
    ]

    for file_name in files_to_create:
        file_path = config_dir / file_name
        if not file_path.exists():
            file_path.touch()


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


def _process_args(args: argparse.Namespace) -> None:
    if args.command == "engine":
        api_main()
    elif args.command == "config":
        sys.stdout.write(json.dumps(ConfigManager().user_config, indent=2))
    elif args.command == "update":
        subprocess.run(f"curl -LsSf {INSTALL_SCRIPT} | bash", shell=True, check=True)  # noqa: S602
    else:
        msg = f"Unknown command: {args.command}"
        raise ValueError(msg)


if __name__ == "__main__":
    main()
