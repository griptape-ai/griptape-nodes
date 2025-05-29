"""Griptape Nodes package."""
# ruff: noqa: S603, S607

from rich.console import Console

console = Console()

with console.status("Loading Griptape Nodes...") as status:
    import argparse
    import importlib.metadata
    import json
    import os
    import shutil
    import sys
    import tarfile
    import tempfile
    from pathlib import Path
    from typing import Literal

    import httpx
    from dotenv import load_dotenv
    from rich.panel import Panel
    from rich.progress import Progress
    from rich.prompt import Confirm, Prompt
    from xdg_base_dirs import xdg_config_home, xdg_data_home

    from griptape_nodes.app import start_app
    from griptape_nodes.retained_mode.griptape_nodes import engine_version
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.os_manager import OSManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

CONFIG_DIR = xdg_config_home() / "griptape_nodes"
DATA_DIR = xdg_data_home() / "griptape_nodes"
ENV_FILE = CONFIG_DIR / ".env"
CONFIG_FILE = CONFIG_DIR / "griptape_nodes_config.json"
LATEST_TAG = "latest"
PACKAGE_NAME = "griptape-nodes"
NODES_APP_URL = "https://nodes.griptape.ai"
NODES_TARBALL_URL = "https://github.com/griptape-ai/griptape-nodes/archive/refs/tags/{tag}.tar.gz"
PYPI_UPDATE_URL = "https://pypi.org/pypi/{package}/json"
GITHUB_UPDATE_URL = "https://api.github.com/repos/griptape-ai/{package}/git/refs/tags/{revision}"


config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)
os_manager = OSManager()


def main() -> None:
    """Main entry point for the Griptape Nodes CLI."""
    load_dotenv(ENV_FILE, override=True)

    # Hack to make paths "just work". # noqa: FIX004
    # Without this, packages like `nodes` don't properly import.
    # Long term solution could be to make `nodes` a proper src-layout package
    # but current engine relies on importing files rather than packages.
    sys.path.append(str(Path.cwd()))

    args = _get_args()
    _process_args(args)


def _run_init(
    *, workspace_directory: str | None = None, api_key: str | None = None, register_advanced_library: bool | None = None
) -> None:
    """Runs through the engine init steps.

    Args:
        workspace_directory (str | None): The workspace directory to set.
        api_key (str | None): The API key to set.
        register_advanced_library (bool | None): Whether to register the advanced library.
    """
    __init_system_config()
    _prompt_for_workspace(workspace_directory=workspace_directory)
    _prompt_for_api_key(api_key=api_key)
    _prompt_for_libraries_to_register(register_advanced_library=register_advanced_library)
    _sync_assets()
    console.print("[bold green]Initialization complete![/bold green]")


def _start_engine(*, no_update: bool = False) -> None:
    """Starts the Griptape Nodes engine.

    Args:
        no_update (bool): If True, skips the auto-update check.
    """
    if not CONFIG_DIR.exists():
        # Default init flow if there is no config directory
        console.print("[bold green]Config directory not found. Initializing...[/bold green]")
        _run_init(
            workspace_directory=os.getenv("GTN_WORKSPACE_DIRECTORY"),
            api_key=os.getenv("GTN_API_KEY"),
            register_advanced_library=os.getenv("GTN_REGISTER_ADVANCED_LIBRARY", "false").lower() == "true",
        )

    # Confusing double negation -- If `no_update` is set, we want to skip the update
    if not no_update:
        _auto_update_self()

    console.print("[bold green]Starting Griptape Nodes engine...[/bold green]")
    start_app()


def _get_args() -> argparse.Namespace:
    """Parse CLI arguments for the *griptape-nodes* entry-point."""
    parser = argparse.ArgumentParser(
        prog="griptape-nodes",
        description="Griptape Nodes Engine.",
    )

    # Global options (apply to every command)
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Skip the auto-update check.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        required=False,
    )

    init_parser = subparsers.add_parser("init", help="Initialize engine configuration.")
    init_parser.add_argument(
        "--api-key",
        help="Set the Griptape Nodes API key.",
        default=os.getenv("GTN_API_KEY", None),
    )
    init_parser.add_argument(
        "--workspace-directory",
        help="Set the Griptape Nodes workspace directory.",
        default=os.getenv("GTN_WORKSPACE_DIRECTORY", None),
    )
    register_advanced_library = os.getenv("GTN_REGISTER_ADVANCED_LIBRARY", None)
    init_parser.add_argument(
        "--register-advanced-library",
        default=register_advanced_library.lower() == "true" if register_advanced_library is not None else None,
        help="Install the Griptape Nodes Advanced Image Library.",
    )

    # engine
    subparsers.add_parser("engine", help="Run the Griptape Nodes engine.")

    # config
    config_parser = subparsers.add_parser("config", help="Manage configuration.")
    config_subparsers = config_parser.add_subparsers(
        dest="subcommand",
        metavar="SUBCOMMAND",
        required=True,
    )
    config_subparsers.add_parser("show", help="Show configuration values.")
    config_subparsers.add_parser("list", help="List configuration values.")
    config_subparsers.add_parser("reset", help="Reset configuration to defaults.")

    # self
    self_parser = subparsers.add_parser("self", help="Manage this CLI installation.")
    self_subparsers = self_parser.add_subparsers(
        dest="subcommand",
        metavar="SUBCOMMAND",
        required=True,
    )
    self_subparsers.add_parser("update", help="Update the CLI.")
    self_subparsers.add_parser("uninstall", help="Uninstall the CLI.")
    self_subparsers.add_parser("version", help="Print the CLI version.")

    # assets
    assets_parser = subparsers.add_parser("assets", help="Manage local assets (libraries, workflows, etc.).")
    assets_subparsers = assets_parser.add_subparsers(
        dest="subcommand",
        metavar="SUBCOMMAND",
        required=True,
    )
    assets_subparsers.add_parser("sync", help="Sync assets with your current engine version.")

    args = parser.parse_args()

    # Default to the `engine` command when none is given.
    if args.command is None:
        args.command = "engine"

    return args


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

        default_api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY", should_error_on_not_found=False)
        while api_key is None:
            api_key = Prompt.ask(
                "Griptape API Key",
                default=default_api_key,
                show_default=True,
            )

    secrets_manager.set_secret("GT_CLOUD_API_KEY", api_key)
    console.print("[bold green]Griptape API Key set")


def _prompt_for_workspace(*, workspace_directory: str | None) -> None:
    """Prompts the user for their workspace directory and stores it in config directory."""
    if workspace_directory is None:
        explainer = """[bold cyan]Workspace Directory[/bold cyan]
        Select the workspace directory. This is the location where Griptape Nodes will store your saved workflows.
        You may enter a custom directory or press Return to accept the default workspace directory"""
        console.print(Panel(explainer, expand=False))

        default_workspace_directory = workspace_directory or config_manager.get_config_value("workspace_directory")
        while workspace_directory is None:
            try:
                workspace_to_test = Prompt.ask(
                    "Workspace Directory",
                    default=default_workspace_directory,
                    show_default=True,
                )
                # Try to resolve the path to check if it exists
                if workspace_to_test is not None:
                    Path(workspace_to_test).expanduser().resolve()
                workspace_directory = workspace_to_test
            except OSError as e:
                console.print(f"[bold red]Invalid workspace directory: {e}[/bold red]")
            except json.JSONDecodeError as e:
                console.print(f"[bold red]Error reading config file: {e}[/bold red]")

    workspace_path = Path(workspace_directory).expanduser().resolve()
    config_manager.set_config_value("workspace_directory", str(workspace_path))

    console.print(f"[bold green]Workspace directory set to: {config_manager.workspace_path}[/bold green]")


def _prompt_for_libraries_to_register(*, register_advanced_library: bool | None = None) -> None:
    """Prompts the user for the libraries to register and stores them in config directory."""
    if register_advanced_library is None:
        explainer = """[bold cyan]Advanced Media Library[/bold cyan]
        Would you like to install the Griptape Nodes Advanced Media Library?
        This node library makes advanced media generation and manipulation nodes available.
        For example, nodes are available for Flux AI image upscaling, or to leverage CUDA for GPU-accelerated image generation.
        CAVEAT: Installing this library requires additional dependencies to download and install, which can take several minutes.
        The Griptape Nodes Advanced Media Library can be added later by following instructions here: [bold blue][link=https://docs.griptapenodes.com]https://docs.griptapenodes.com[/link][/bold blue].
        """
        console.print(Panel(explainer, expand=False))

    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/929
    key = "app_events.on_app_initialization_complete.libraries_to_register"
    current_libraries = config_manager.get_config_value(
        key,
        config_source="user_config",
        default=config_manager.get_config_value(key, config_source="default_config", default=[]),
    )
    default_library = str(
        xdg_data_home() / "griptape_nodes/libraries/griptape_nodes_library/griptape_nodes_library.json"
    )
    extra_libraries = [
        str(
            xdg_data_home()
            / "griptape_nodes/libraries/griptape_nodes_advanced_media_library/griptape_nodes_library.json"
        )
    ]
    libraries_to_merge = [default_library]

    if register_advanced_library is None:
        register_extras = Confirm.ask("Register Advanced Media Library?", default=False)
    else:
        register_extras = register_advanced_library

    if register_extras:
        libraries_to_merge.extend(extra_libraries)

    # Remove duplicates
    merged_libraries = list(set(current_libraries + libraries_to_merge))

    config_manager.set_config_value("app_events.on_app_initialization_complete.libraries_to_register", merged_libraries)


def _get_latest_version(package: str, install_source: str) -> str:
    """Fetches the latest release tag from PyPI.

    Args:
        package: The name of the package to fetch the latest version for.
        install_source: The source from which the package is installed (e.g., "pypi", "git", "file").

    Returns:
        str: Latest release tag (e.g., "v0.31.4")
    """
    if install_source == "pypi":
        update_url = PYPI_UPDATE_URL.format(package=package)

        with httpx.Client() as client:
            response = client.get(update_url)
            try:
                response.raise_for_status()
                data = response.json()
                return f"v{data['info']['version']}"
            except httpx.HTTPStatusError as e:
                console.print(f"[red]Error fetching latest version: {e}[/red]")
                return __get_current_version()
    elif install_source == "git":
        # We only install auto updating from the 'latest' tag
        revision = LATEST_TAG
        update_url = GITHUB_UPDATE_URL.format(package=package, revision=revision)

        with httpx.Client() as client:
            response = client.get(update_url)
            try:
                response.raise_for_status()
                # Get the latest commit SHA for the tag, this effectively the latest version of the package
                data = response.json()
                if "object" in data and "sha" in data["object"]:
                    return data["object"]["sha"][:7]
                # Should not happen, but if it does, return the current version
                return __get_current_version()
            except httpx.HTTPStatusError as e:
                console.print(f"[red]Error fetching latest version: {e}[/red]")
                return __get_current_version()
    else:
        # If the package is installed from a file, just return the current version since the user is likely managing it manually
        return __get_current_version()


def _auto_update_self() -> None:
    """Automatically updates the script to the latest version if the user confirms."""
    console.print("[bold green]Checking for updates...[/bold green]")
    source, commit_id = __get_install_source()
    current_version = __get_current_version()
    latest_version = _get_latest_version(PACKAGE_NAME, source)

    if source == "git" and commit_id is not None:
        can_update = commit_id != latest_version
        update_message = f"Your current engine version, {current_version} ({source} - {commit_id}), doesn't match the latest release, {latest_version}. Update now?"
    else:
        can_update = current_version < latest_version
        update_message = f"Your current engine version, {current_version}, is behind the latest release, {latest_version}. Update now?"

    if can_update:
        update = Confirm.ask(update_message, default=True)

        if update:
            _update_self()


def _update_self() -> None:
    """Installs the latest release of the CLI *and* refreshes bundled assets."""
    console.print("[bold green]Starting updater...[/bold green]")

    os_manager.replace_process([sys.executable, "-m", "griptape_nodes.updater"])


def _sync_assets() -> None:
    """Download and fully replace the Griptape Nodes assets directory."""
    install_source, _ = __get_install_source()
    # Unless we're installed from PyPi, grab assets from the 'latest' tag
    if install_source == "pypi":
        version = __get_current_version()
    else:
        version = LATEST_TAG

    console.print(f"[bold cyan]Fetching Griptape Nodes assets ({version})...[/bold cyan]")

    tar_url = NODES_TARBALL_URL.format(tag=version)
    console.print(f"[green]Downloading from {tar_url}[/green]")
    dest_nodes = DATA_DIR / "libraries"

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "nodes.tar.gz"

        # Streaming download with a tiny progress bar
        with httpx.stream("GET", tar_url, follow_redirects=True) as r, Progress() as progress:
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                console.print(f"[red]Error fetching assets: {e}[/red]")
                return
            task = progress.add_task("[green]Downloading...", total=int(r.headers.get("Content-Length", 0)))
            with tar_path.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))

        console.print("[green]Extracting...[/green]")
        # Extract and locate extracted directory
        with tarfile.open(tar_path) as tar:
            tar.extractall(tmp, filter="data")

        extracted_root = next(Path(tmp).glob("griptape-nodes-*"))
        extracted_libs = extracted_root / "libraries"

        # Fully replace the destination directory
        if dest_nodes.exists():
            shutil.rmtree(dest_nodes)
        shutil.copytree(extracted_libs, dest_nodes)

    console.print("[bold green]Node Libraries updated.[/bold green]")


def _print_current_version() -> None:
    """Prints the current version of the script."""
    version = __get_current_version()
    source, commit_id = __get_install_source()
    if commit_id is None:
        console.print(f"[bold green]{version} ({source})[/bold green]")
    else:
        console.print(f"[bold green]{version} ({source} - {commit_id})[/bold green]")


def _print_user_config() -> None:
    """Prints the user configuration from the config file."""
    config = config_manager.merged_config
    sys.stdout.write(json.dumps(config, indent=2))


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
    console.print("[bold]Removing config and data directories...[/bold]")
    dirs = [(CONFIG_DIR, "Config Dir"), (DATA_DIR, "Data Dir")]
    caveats = []
    for dir_path, dir_name in dirs:
        if dir_path.exists():
            console.print(f"[bold]Removing {dir_name} '{dir_path}'...[/bold]")
            try:
                shutil.rmtree(dir_path)
            except OSError as exc:
                console.print(f"[red]Error removing {dir_name} '{dir_path}': {exc}[/red]")
                caveats.append(
                    f"- [red]Error removing {dir_name} '{dir_path}'. You may want remove this directory manually.[/red]"
                )
        else:
            console.print(f"[yellow]{dir_name} '{dir_path}' does not exist; skipping.[/yellow]")

    # Handle any remaining config files not removed by design
    remaining_config_files = config_manager.config_files
    if remaining_config_files:
        caveats.append("- Some config files were intentionally not removed:")
        caveats.extend(f"\t[yellow]- {file}[/yellow]" for file in remaining_config_files)

    # If there were any caveats to the uninstallation process, print them
    if caveats:
        console.print("[bold]Caveats:[/bold]")
        for line in caveats:
            console.print(line)

    # Remove the executable
    console.print("[bold]Removing the executable...[/bold]")
    console.print("[bold yellow]When done, press Enter to exit.[/bold yellow]")
    os_manager.replace_process(["uv", "tool", "uninstall", "griptape-nodes"])


def _process_args(args: argparse.Namespace) -> None:  # noqa: C901, PLR0912
    if args.command == "init":
        _run_init(
            workspace_directory=args.workspace_directory,
            api_key=args.api_key,
            register_advanced_library=args.register_advanced_library,
        )
    elif args.command == "engine":
        _start_engine(no_update=args.no_update)
    elif args.command == "config":
        if args.subcommand == "list":
            _list_user_configs()
        elif args.subcommand == "reset":
            _reset_user_config()
        elif args.subcommand == "show":
            _print_user_config()
    elif args.command == "self":
        if args.subcommand == "update":
            _update_self()
        elif args.subcommand == "uninstall":
            _uninstall_self()
        elif args.subcommand == "version":
            _print_current_version()
    elif args.command == "assets":
        if args.subcommand == "sync":
            _sync_assets()
    else:
        msg = f"Unknown command: {args.command}"
        raise ValueError(msg)


def __get_current_version() -> str:
    """Returns the current version of the Griptape Nodes package."""
    return f"v{engine_version}"


def __get_install_source() -> tuple[Literal["git", "file", "pypi"], str | None]:
    """Determines the install source of the Griptape Nodes package.

    Returns:
        tuple: A tuple containing the install source and commit ID (if applicable).
    """
    dist = importlib.metadata.distribution("griptape_nodes")
    direct_url_text = dist.read_text("direct_url.json")
    # installing from pypi doesn't have a direct_url.json file
    if direct_url_text is None:
        return "pypi", None

    direct_url_info = json.loads(direct_url_text)
    url = direct_url_info.get("url")
    if url.startswith("file://"):
        return "file", None
    if "vcs_info" in direct_url_info:
        return "git", direct_url_info["vcs_info"].get("commit_id")[:7]
    # Fall back to pypi if no other source is found
    return "pypi", None


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
            with Path.open(file_path, "w", encoding="utf-8") as file:
                file.write(file_name[1])


if __name__ == "__main__":
    main()
