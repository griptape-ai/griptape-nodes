"""Griptape Nodes package."""

# ruff: noqa: S603, S607
import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import webbrowser
from pathlib import Path

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.prompt import Confirm, Prompt
from xdg_base_dirs import xdg_config_home, xdg_data_home

from griptape_nodes.app import start_app
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

CONFIG_DIR = xdg_config_home() / "griptape_nodes"
DATA_DIR = xdg_data_home() / "griptape_nodes"
ENV_FILE = CONFIG_DIR / ".env"
CONFIG_FILE = CONFIG_DIR / "griptape_nodes_config.json"
REPO_NAME = "griptape-ai/griptape-nodes"
NODES_APP_URL = "https://nodes.griptape.ai"
NODES_TARBALL_URL = "https://github.com/griptape-ai/griptape-nodes/archive/refs/tags/{tag}.tar.gz"


console = Console()
config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)


def main() -> None:
    """Main entry point for the Griptape Nodes CLI."""
    load_dotenv(ENV_FILE)

    # Hack to make paths "just work". # noqa: FIX004
    # Without this, packages like `nodes` don't properly import.
    # Long term solution could be to make `nodes` a proper src-layout package
    # but current engine relies on importing files rather than packages.
    sys.path.append(str(Path.cwd()))

    args = _get_args()
    _process_args(args)


def _run_init(api_key: str | None = None, workspace_directory: str | None = None) -> None:
    """Runs through the engine init steps, optionally skipping prompts if the user provided `--api-key`."""
    __init_system_config()
    _prompt_for_workspace(workspace_directory)
    _prompt_for_api_key(api_key)

    latest_tag = _get_latest_version(REPO_NAME)
    _install_nodes_assets(tag=latest_tag)


def _get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="griptape-nodes", description="Griptape Nodes Engine.")

    parser.add_argument(
        "command",
        help="Command to run",
        nargs="?",
        choices=["init", "engine", "config", "update", "uninstall", "version"],
        default="engine",
    )

    # Optional subcommand for 'config' (e.g., config list)
    parser.add_argument(
        "config_subcommand",
        help="Subcommand for 'config'",
        nargs="?",
        choices=["list", "reset"],
        default=None,
    )

    # Optionally allow setting the API key or workspace directory directly for the init command
    parser.add_argument(
        "--api-key",
        help="Override the Griptape Nodes API key when running 'init'.",
        required=False,
    )
    parser.add_argument(
        "--workspace-directory",
        help="Override the Griptape Nodes workspace directory when running 'init'.",
        required=False,
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Skip the auto-update check.",
        required=False,
    )

    return parser.parse_args()


def _prompt_for_api_key(api_key: str | None = None) -> None:
    """Prompts the user for their GT_CLOUD_API_KEY unless it's provided."""
    if api_key is None:
        explainer = f"""[bold cyan]Griptape API Key[/bold cyan]
        A Griptape API Key is needed to proceed.
        This key allows the Griptape Nodes Engine to communicate with the Griptape Nodes Editor.
        In order to get your key, return to the [link={NODES_APP_URL}]{NODES_APP_URL}[/link] tab in your browser and click the button
        "Generate API Key".
        Once the key is generated, copy and paste its value here to proceed."""
        console.print(Panel(explainer, expand=False))

    default_key = api_key or secrets_manager.get_secret("GT_CLOUD_API_KEY", should_error_on_not_found=False)
    # If api_key is provided via --api-key, we don't want to prompt for it
    current_key = api_key
    while current_key is None:
        current_key = Prompt.ask(
            "Griptape API Key",
            default=default_key,
            show_default=True,
        )

    secrets_manager.set_secret("GT_CLOUD_API_KEY", current_key)


def _prompt_for_workspace(workspace_directory_arg: str | None) -> None:
    """Prompts the user for their workspace directory and stores it in config directory."""
    explainer = """[bold cyan]Workspace Directory[/bold cyan]
    Select the workspace directory. This is the location where Griptape Nodes will store your saved workflows.
    You may enter a custom directory or press Return to accept the default workspace directory"""
    console.print(Panel(explainer, expand=False))

    valid_workspace = False
    default_workspace_directory = workspace_directory_arg or config_manager.get_config_value("workspace_directory")
    while not valid_workspace:
        try:
            workspace_directory = Prompt.ask(
                "Workspace Directory",
                default=default_workspace_directory,
                show_default=True,
            )
            workspace_path = Path(workspace_directory).expanduser().resolve()

            config_manager.workspace_path = workspace_path
            config_manager.set_config_value("workspace_directory", str(workspace_path))

            valid_workspace = True
        except OSError as e:
            console.print(f"[bold red]Invalid workspace directory: {e}[/bold red]")
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error reading config file: {e}[/bold red]")
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
            default=True,
        )

        if update:
            _install_latest_release(run_after_install=True)


def _install_latest_release(*, run_after_install: bool = False) -> None:
    """Installs the latest release of the CLI *and* refreshes bundled assets."""
    console.print("[bold green]Starting update…[/bold green]")

    try:
        __download_and_run_installer()
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during update: {e}[/bold red]")
        sys.exit(1)

    latest_tag = _get_latest_version(REPO_NAME)
    _install_nodes_assets(tag=latest_tag)

    console.print("[bold green]Update complete![/bold green]")

    if run_after_install:
        # Restart the executable itself
        os.execv(sys.argv[0], sys.argv)  # noqa: S606
    sys.exit(0)


def _install_nodes_assets(tag: str = "latest") -> None:
    """Download the release tarball identified."""
    console.print(f"[bold cyan]Fetching Griptape Nodes assets ({tag})…[/bold cyan]")
    tar_url = NODES_TARBALL_URL.format(tag=tag)
    dest_nodes = DATA_DIR / "nodes"
    dest_workflows = DATA_DIR / "workflows"

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "nodes.tar.gz"

        # Streaming download with a tiny progress bar
        with httpx.stream("GET", tar_url, follow_redirects=True) as r, Progress() as progress:
            r.raise_for_status()
            task = progress.add_task("[green]downloading…", total=int(r.headers.get("Content-Length", 0)))
            with tar_path.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))

        # Extract and copy
        with tarfile.open(tar_path) as tar:
            tar.extractall(tmp, filter="data")

        extracted_root = next(Path(tmp).glob("griptape-nodes-*"))

        console.print("[yellow]Copying nodes directory…[/yellow]")
        shutil.copytree(extracted_root / "nodes", dest_nodes, dirs_exist_ok=True)
        console.print("[yellow]Copying workflows directory…[/yellow]")
        shutil.copytree(extracted_root / "workflows", dest_workflows, dirs_exist_ok=True)

    console.print("[bold green]Nodes + Workflows updated.[/bold green]")


def __download_and_run_installer() -> None:
    """Runs the update commands for the engine."""
    try:
        subprocess.run(
            ["uv", "tool", "upgrade", "griptape-nodes"],
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during update: {e}[/bold red]")


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


def _list_user_configs() -> None:
    """Lists user configuration files in ascending precedence."""
    num_config_files = len(config_manager.config_files)
    console.print(
        f"[bold]User Configuration Files (lowest precedence (1.) ⟶ highest precedence ({num_config_files}.)):[/bold]"
    )
    for idx, config in enumerate(config_manager.config_files):
        console.print(f"[green]{idx + 1}. {config}[/green]")


def _reset_user_config() -> None:
    """Resets the user configuration to the default values."""
    console.print("[bold]Resetting user configuration to default values...[/bold]")
    config_manager.reset_user_config()
    console.print("[bold green]User configuration reset complete![/bold green]")


def _uninstall_self() -> None:
    """Uninstalls itself by removing config/data directories and the executable."""
    console.print("[bold]Uninstalling Griptape Nodes...[/bold]")

    # Remove config and data directories
    dirs = [(CONFIG_DIR, "Config Dir"), (DATA_DIR, "Data Dir")]
    for dir_path, dir_name in dirs:
        if dir_path.exists():
            console.print(f"[bold]Removing {dir_name} '{dir_path}'...[/bold]")
            try:
                shutil.rmtree(dir_path)
            except OSError as exc:
                console.print(f"[red]Error removing {dir_name} '{dir_path}': {exc}[/red]")
        else:
            console.print(f"[yellow]{dir_name} '{dir_path}' does not exist; skipping.[/yellow]")

    # Remove the executable/tool
    executable_removed = __uninstall_executable()

    caveats = []
    # Handle any remaining config files not removed by design
    remaining_config_files = config_manager.config_files
    if remaining_config_files:
        caveats.append("- Some config files were intentionally not removed:")
        caveats.extend(f"\t[yellow]- {file}[/yellow]" for file in remaining_config_files)

    if not executable_removed:
        caveats.append(
            "- The uninstaller was not able to remove the Griptape Nodes executable. "
            "Please remove the executable manually by running '[bold]uv tool uninstall griptape-nodes[/bold]'."
        )

    # If there were any caveats to the uninstallation process, print them
    if caveats:
        console.print("[bold]Caveats:[/bold]")
        for line in caveats:
            console.print(line)

    # Exit the process
    sys.exit(0)


def _process_args(args: argparse.Namespace) -> None:  # noqa: C901
    if args.command == "init":
        _run_init(api_key=args.api_key, workspace_directory=args.workspace_directory)
        console.print("Initialization complete! You can now run the engine with 'griptape-nodes' (or just 'gtn').")
    elif args.command == "engine":
        if not CONFIG_DIR.exists():
            # Default init flow if there is no config directory
            _run_init()
            webbrowser.open(NODES_APP_URL)

        # Confusing double negation -- If `no_update` is set, we want to skip the update
        if not args.no_update:
            _auto_update()

        start_app()
    elif args.command == "config":
        if args.config_subcommand == "list":
            _list_user_configs()
        if args.config_subcommand == "reset":
            _reset_user_config()
        else:
            sys.stdout.write(json.dumps(_get_user_config(), indent=2))
    elif args.command == "update":
        _install_latest_release()
    elif args.command == "uninstall":
        _uninstall_self()
    elif args.command == "version":
        version = _get_current_version()
        console.print(f"[bold green]{version}[/bold green]")
    else:
        msg = f"Unknown command: {args.command}"
        raise ValueError(msg)


def __uninstall_executable() -> bool:
    """Uninstalls the Griptape Nodes executable.

    This is skipped on Windows due to OS limitations.

    Returns:
        bool: True if the executable was removed, False otherwise.

    """
    executable_path = shutil.which("griptape-nodes")
    executable_removed = False
    if executable_path:
        if OSManager.is_windows():
            console.print(
                "[bold]Windows does not allow for uninstalling executables while they are running. Please review uninstallation caveats for manual steps.[/bold]"
            )
        else:
            console.print(f"[bold]Removing Griptape Nodes executable ({executable_path})...[/bold]")
            try:
                subprocess.run(
                    ["uv", "tool", "uninstall", "griptape-nodes"],
                    check=True,
                    text=True,
                )
                executable_removed = True
            except subprocess.CalledProcessError:
                executable_removed = False
    else:
        console.print("[yellow]Griptape Nodes executable not found; skipping removal.[/yellow]")

    console.print("[bold green]Uninstall complete![/bold green]")

    return executable_removed


def __init_system_config() -> None:
    """Initializes the system config directory if it doesn't exist."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    files_to_create = [
        (ENV_FILE, ""),
        (CONFIG_FILE, "{}"),
    ]

    for file_name in files_to_create:
        file_path = CONFIG_DIR / file_name[0]
        if not file_path.exists():
            with Path.open(file_path, "w") as file:
                file.write(file_name[1])


if __name__ == "__main__":
    main()
