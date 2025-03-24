"""Griptape Nodes package."""

import argparse
import json
import sys
from pathlib import Path

from griptape_nodes.api.app import main as api_main
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager


def main() -> None:
    # Hack to make paths "just work". # noqa: FIX004
    # Without this, packages like `nodes` don't properly import.
    # Long term solution could be to make `nodes` a proper src-layout package
    # but current engine relies on importing files rather than packages.
    sys.path.append(str(Path.cwd()))

    args = _get_args()
    _process_args(args)


def _get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="griptape-nodes", description="Griptape Nodes Engine.")
    parser.add_argument("command", help="Command to run", nargs="?", choices=["engine", "config"], default="engine")
    return parser.parse_args()


def _process_args(args: argparse.Namespace) -> None:
    if args.command == "engine":
        api_main()
    elif args.command == "config":
        sys.stdout.write(json.dumps(ConfigManager().user_config, indent=2))
    else:
        msg = f"Unknown command: {args.command}"
        raise ValueError(msg)


if __name__ == "__main__":
    main()
