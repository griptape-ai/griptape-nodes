"""Griptape Nodes package."""

# ruff: noqa: S603, S607

import argparse
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv, set_key
from dotenv.main import DotEnv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from xdg_base_dirs import xdg_config_home, xdg_data_home

from griptape_nodes.app import start_app
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

GH_INSTALL_SCRIPT_SH = "/repos/griptape-ai/griptape-nodes/contents/install.sh?ref=main"
GH_INSTALL_SCRIPT_PS = "/repos/griptape-ai/griptape-nodes/contents/install.ps1?ref=main"
INSTALL_SCRIPT_SH = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/install.sh"
INSTALL_SCRIPT_PS = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/install.ps1"
CONFIG_DIR = xdg_config_home() / "griptape_nodes"
DATA_DIR = xdg_data_home() / "griptape_nodes"
ENV_FILE = CONFIG_DIR / ".env"
CONFIG_FILE = CONFIG_DIR / "griptape_nodes_config.json"
REPO_NAME = "griptape-ai/griptape-nodes"
NODES_APP_URL = "https://nodes.griptape.ai"


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


def _run_init(api_key: str | None = None, workspace_directory: str | None = None) -> None:
    """Runs through the engine init steps, optionally skipping prompts if the user provided `--api-key`."""
    _prompt_for_workspace(workspace_directory)
    _prompt_for_api_key(api_key)


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
        choices=["list"],
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


def _init_system_config() -> bool:
    """Initializes the system config directory if it doesn't exist.

    Returns:
        bool: True if the system config directory was created, False otherwise.

    """
    is_first_init = False
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        is_first_init = True

    files_to_create = [
        (ENV_FILE, ""),
        (CONFIG_FILE, "{}"),
    ]

    for file_name in files_to_create:
        file_path = CONFIG_DIR / file_name[0]
        if not file_path.exists():
            with Path.open(file_path, "w") as file:
                file.write(file_name[1])

    return is_first_init


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

    default_key = api_key or DotEnv(ENV_FILE, verbose=False).get("GT_CLOUD_API_KEY")
    # If api_key is provided via --api-key, we don't want to prompt for it
    current_key = api_key
    while current_key is None:
        current_key = Prompt.ask(
            "Griptape API Key",
            default=default_key,
            show_default=True,
        )

    set_key(ENV_FILE, "GT_CLOUD_API_KEY", current_key)
    config_manager.set_config_value("nodes.Griptape.GT_CLOUD_API_KEY", "$GT_CLOUD_API_KEY")
    secrets_manager.set_secret("GT_CLOUD_API_KEY", current_key)
    console.print(f"[bold green]API Key set to: {current_key}[/bold green]")


def _prompt_for_workspace(workspace_directory_arg: str | None) -> None:
    """Prompts the user for their workspace directory and stores it in config directory."""
    if workspace_directory_arg is not None:
        try:
            workspace_path = Path(workspace_directory_arg).expanduser().resolve()
        except OSError as e:
            console.print(f"[bold red]Invalid workspace directory argument: {e}[/bold red]")
        else:
            config_manager.workspace_path = str(workspace_path)
            console.print(f"[bold green]Workspace directory set to: {config_manager.workspace_path}[/bold green]")
            return

    explainer = """[bold cyan]Workspace Directory[/bold cyan]
    Select the workspace directory. This is the location where Griptape Nodes will store your saved workflows, configuration data, and secrets.
    You may enter a custom directory or press Return to accept the default workspace directory"""
    console.print(Panel(explainer, expand=False))

    valid_workspace = False
    default_workspace_directory = config_manager.get_config_value("workspace_directory")
    while not valid_workspace:
        try:
            workspace_directory = Prompt.ask(
                "Workspace Directory",
                default=default_workspace_directory,
                show_default=True,
            )
            config_manager.workspace_path = str(Path(workspace_directory).expanduser().resolve())
            valid_workspace = True
        except OSError as e:
            console.print(f"[bold red]Invalid workspace directory: {e}[/bold red]")
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
            _install_latest_release()


def _install_latest_release() -> None:
    """Installs the latest release of the script. Prefers GitHub CLI if available."""
    console.print("[bold green]Starting update...[/bold green]")
    console.print("[bold yellow]Checking for GitHub CLI...[/bold yellow]")

    try:
        __download_and_run_installer()
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during update: {e}[/bold red]")
        sys.exit(1)

    console.print(
        "[bold green]Update complete! Restart the engine by running 'griptape-nodes' (or just 'gtn').[/bold green]"
    )
    sys.exit(0)


def __download_and_run_installer() -> None:
    """Runs the update commands for the engine."""
    gh_cli = shutil.which("gh")
    if gh_cli:
        console.print("[bold green]Found GitHub CLI. Using gh to fetch install script...[/bold green]")

        if OSManager.is_windows():
            # Fetch install.ps1 contents using gh
            ps_content = subprocess.check_output(
                [
                    gh_cli,
                    "api",
                    "-H",
                    "Accept: application/vnd.github.v3.raw",
                    GH_INSTALL_SCRIPT_PS,
                ],
                text=True,
            )
            # Run the PowerShell script from stdin
            subprocess.run(
                ["powershell", "-ExecutionPolicy", "ByPass", "-Command", "-"],
                input=ps_content,
                text=True,
                check=True,
            )
        else:
            # macOS or Linux
            bash_content = subprocess.check_output(
                [
                    gh_cli,
                    "api",
                    "-H",
                    "Accept: application/vnd.github.v3.raw",
                    GH_INSTALL_SCRIPT_SH,
                ],
                text=True,
            )
            # Run the Bash script from stdin
            subprocess.run(
                ["bash"],
                input=bash_content,
                capture_output=True,
                text=True,
                check=True,
            )
    else:
        console.print("[bold yellow]GitHub CLI not found. Falling back to direct download...[/bold yellow]")

        if OSManager.is_windows():
            subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "ByPass",
                    "-c",
                    f"irm {INSTALL_SCRIPT_PS} | iex",
                ],
                check=True,
                text=True,
            )
        else:
            curl_process = subprocess.run(
                [
                    "curl",
                    "-LsSf",
                    INSTALL_SCRIPT_SH,
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            curl_process.check_returncode()
            subprocess.run(
                ["bash"],
                input=curl_process.stdout,
                capture_output=True,
                check=True,
                text=True,
            )


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
    """Lists the user configuration files."""
    for config in config_manager.config_files:
        console.print(f"[bold green]{config}[/bold green]")


def _uninstall_self() -> None:
    """Uninstalls itself by removing config/data directories and the executable."""
    console.print("[bold]Uninstalling Griptape Nodes...[/bold]")

    # Remove config directory
    if CONFIG_DIR.exists():
        console.print(f"[bold]Removing config directory '{CONFIG_DIR}'...[/bold]")
        try:
            shutil.rmtree(CONFIG_DIR)
        except OSError as exc:
            console.print(f"[red]Error removing config directory '{CONFIG_DIR}': {exc}[/red]")
    else:
        console.print(f"[yellow]Config directory '{CONFIG_DIR}' does not exist; skipping.[/yellow]")

    # Remove data directory
    if DATA_DIR.exists():
        console.print(f"[bold]Removing data directory '{DATA_DIR}'...[/bold]")
        try:
            shutil.rmtree(DATA_DIR)
        except OSError as exc:
            console.print(f"[bold]Error removing data directory '{DATA_DIR}': {exc}[/bold]")
    else:
        console.print(f"[yellow]Data directory '{DATA_DIR}' does not exist; skipping.[/yellow]")

    # Remove the executable/tool
    executable_path = shutil.which("griptape-nodes")
    executable_removed = False
    if executable_path:
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

    if caveats:
        console.print("[bold]Caveats:[/bold]")
        for line in caveats:
            console.print(line)

    # Exit the process
    sys.exit(0)


def _process_args(args: argparse.Namespace) -> None:
    is_first_init = _init_system_config()

    if args.command == "init":
        _run_init(api_key=args.api_key, workspace_directory=args.workspace_directory)
        console.print("Initialization complete! You can now run the engine with 'griptape-nodes' (or just 'gtn').")
    elif args.command == "engine":
        if is_first_init:
            # Default init flow if it's truly the first time
            _run_init()

        # Confusing double negation -- If `no_update` is set, we want to skip the update
        if not args.no_update:
            _auto_update()
        start_app()
    elif args.command == "config":
        if args.config_subcommand == "list":
            _list_user_configs()
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


if __name__ == "__main__":
    main()
