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
    from rich.box import HEAVY_EDGE
    from rich.panel import Panel
    from rich.progress import Progress
    from rich.prompt import Confirm, Prompt
    from rich.table import Table
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
GT_CLOUD_BASE_URL = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")

# Environment variable defaults for init configuration
ENV_WORKSPACE_DIRECTORY = os.getenv("GTN_WORKSPACE_DIRECTORY")
ENV_API_KEY = os.getenv("GTN_API_KEY")
ENV_STORAGE_BACKEND = os.getenv("GTN_STORAGE_BACKEND")
ENV_STORAGE_BACKEND_BUCKET_ID = os.getenv("GTN_STORAGE_BACKEND_BUCKET_ID")
ENV_REGISTER_ADVANCED_LIBRARY = (
    os.getenv("GTN_REGISTER_ADVANCED_LIBRARY", "false").lower() == "true"
    if os.getenv("GTN_REGISTER_ADVANCED_LIBRARY") is not None
    else None
)


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


def _run_init(  # noqa: PLR0913
    *,
    interactive: bool = True,
    workspace_directory: str | None = None,
    api_key: str | None = None,
    storage_backend: str | None = None,
    storage_backend_bucket_id: str | None = None,
    register_advanced_library: bool | None = None,
) -> None:
    """Runs through the engine init steps.

    Args:
        interactive (bool): If True, prompts the user for input; otherwise uses provided values.
        workspace_directory (str | None): The workspace directory to set.
        api_key (str | None): The API key to set.
        storage_backend (str | None): The storage backend to set.
        storage_backend_bucket_id (str | None): The storage backend bucket ID to set.
        register_advanced_library (bool | None): Whether to register the advanced library.
    """
    __init_system_config()

    if interactive:
        workspace_directory = _prompt_for_workspace(default_workspace_directory=workspace_directory)
        api_key = _prompt_for_api_key(default_api_key=api_key)
        storage_backend = _prompt_for_storage_backend(default_storage_backend=storage_backend)
        if storage_backend == "gtc":
            storage_backend_bucket_id = _prompt_for_storage_backend_bucket_id(
                default_storage_backend_bucket_id=storage_backend_bucket_id
            )
        register_advanced_library = _prompt_for_advanced_media_library(
            default_prompt_for_advanced_media_library=register_advanced_library
        )
        libraries_to_register = __build_libraries_list(register_advanced_library=register_advanced_library)

    if workspace_directory is not None:
        config_manager.set_config_value("workspace_directory", workspace_directory)
        console.print(f"[bold green]Workspace directory set to: {workspace_directory}[/bold green]")

    if api_key is not None:
        secrets_manager.set_secret("GT_CLOUD_API_KEY", api_key)
        console.print("[bold green]Griptape API Key set")

    if storage_backend is not None:
        config_manager.set_config_value("storage_backend", storage_backend)
        console.print(f"[bold green]Storage backend set to: {storage_backend}")

    if storage_backend_bucket_id is not None:
        secrets_manager.set_secret("GT_CLOUD_BUCKET_ID", storage_backend_bucket_id)
        console.print(f"[bold green]Storage backend bucket ID set to: {storage_backend_bucket_id}[/bold green]")

    if register_advanced_library is not None:
        libraries_to_register = __build_libraries_list(register_advanced_library=register_advanced_library)
        config_manager.set_config_value(
            "app_events.on_app_initialization_complete.libraries_to_register", libraries_to_register
        )
        console.print(f"[bold green]Libraries to register set to: {', '.join(libraries_to_register)}[/bold green]")

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
            workspace_directory=ENV_WORKSPACE_DIRECTORY,
            api_key=ENV_API_KEY,
            storage_backend=ENV_STORAGE_BACKEND,
            storage_backend_bucket_id=ENV_STORAGE_BACKEND_BUCKET_ID,
            register_advanced_library=ENV_REGISTER_ADVANCED_LIBRARY,
            interactive=True,
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
        default=ENV_API_KEY,
    )
    init_parser.add_argument(
        "--workspace-directory",
        help="Set the Griptape Nodes workspace directory.",
        default=ENV_WORKSPACE_DIRECTORY,
    )
    init_parser.add_argument(
        "--storage-backend",
        help="Set the storage backend ('local' or 'gtc').",
        choices=["local", "gtc"],
        default=ENV_STORAGE_BACKEND,
    )
    init_parser.add_argument(
        "--storage-backend-bucket-id",
        help="Set the Griptape Cloud bucket ID (only used with 'gtc' storage backend).",
        default=ENV_STORAGE_BACKEND_BUCKET_ID,
    )
    init_parser.add_argument(
        "--register-advanced-library",
        help="Install the Griptape Nodes Advanced Image Library.",
        default=ENV_REGISTER_ADVANCED_LIBRARY,
    )
    init_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Run init in non-interactive mode (no prompts).",
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


def _prompt_for_api_key(default_api_key: str | None = None) -> str:
    """Prompts the user for their GT_CLOUD_API_KEY unless it's provided."""
    if default_api_key is None:
        default_api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY", should_error_on_not_found=False)
    explainer = f"""[bold cyan]Griptape API Key[/bold cyan]
    A Griptape API Key is needed to proceed.
    This key allows the Griptape Nodes Engine to communicate with the Griptape Nodes Editor.
    In order to get your key, return to the [link={NODES_APP_URL}]{NODES_APP_URL}[/link] tab in your browser and click the button
    "Generate API Key".
    Once the key is generated, copy and paste its value here to proceed."""
    console.print(Panel(explainer, expand=False))

    while True:
        api_key = Prompt.ask(
            "Griptape API Key",
            default=default_api_key,
            show_default=True,
        )
        if api_key:
            break

    return api_key


def _prompt_for_workspace(*, default_workspace_directory: str | None = None) -> str:
    """Prompts the user for their workspace directory."""
    if default_workspace_directory is None:
        default_workspace_directory = config_manager.get_config_value("workspace_directory")
    explainer = """[bold cyan]Workspace Directory[/bold cyan]
    Select the workspace directory. This is the location where Griptape Nodes will store your saved workflows.
    You may enter a custom directory or press Return to accept the default workspace directory"""
    console.print(Panel(explainer, expand=False))

    while True:
        try:
            workspace_to_test = Prompt.ask(
                "Workspace Directory",
                default=default_workspace_directory,
                show_default=True,
            )
            if workspace_to_test:
                workspace_directory = str(Path(workspace_to_test).expanduser().resolve())
                break
        except OSError as e:
            console.print(f"[bold red]Invalid workspace directory: {e}[/bold red]")
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error reading config file: {e}[/bold red]")

    return workspace_directory


def _prompt_for_storage_backend(*, default_storage_backend: str | None = None) -> str:
    """Prompts the user for their storage backend."""
    if default_storage_backend is None:
        default_storage_backend = config_manager.get_config_value("storage_backend")
    explainer = """[bold cyan]Storage Backend[/bold cyan]
Select the storage backend. This is where Griptape Nodes will store your static files.
Enter 'gtc' to use Griptape Cloud Bucket Storage, or press Return to accept the default of the local static file server."""
    console.print(Panel(explainer, expand=False))

    while True:
        try:
            storage_backend = Prompt.ask(
                "Storage Backend",
                choices=["gtc", "local"],
                default=default_storage_backend,
                show_default=True,
            )
            if storage_backend:
                break
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error reading config file: {e}[/bold red]")

    return storage_backend


def _get_griptape_cloud_bucket_ids_and_display_table() -> tuple[list[str], Table]:
    """Fetches the list of Griptape Cloud Bucket IDs from the API."""
    url = f"{GT_CLOUD_BASE_URL}/api/buckets"
    headers = {
        "Authorization": f"Bearer {secrets_manager.get_secret('GT_CLOUD_API_KEY')}",
    }
    bucket_ids: list[str] = []

    table = Table(show_header=True, box=HEAVY_EDGE, show_lines=True, expand=True)
    table.add_column("Bucket Name", style="green")
    table.add_column("Bucket ID", style="green")

    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        try:
            response.raise_for_status()
            data = response.json()
            for bucket in data["buckets"]:
                bucket_ids.append(bucket["bucket_id"])
                table.add_row(bucket["name"], bucket["bucket_id"])

        except httpx.HTTPStatusError as e:
            console.print(f"[red]Error fetching bucket IDs: {e}[/red]")

    return bucket_ids, table


def _prompt_for_storage_backend_bucket_id(*, default_storage_backend_bucket_id: str | None = None) -> str:
    """Prompts the user for their storage backend bucket ID."""
    if default_storage_backend_bucket_id is None:
        default_storage_backend_bucket_id = secrets_manager.get_secret(
            "GT_CLOUD_BUCKET_ID", should_error_on_not_found=False
        )
    explainer = """[bold cyan]Storage Backend Bucket ID[/bold cyan]
Enter the Griptape Cloud Bucket ID to use for Griptape Cloud Storage. This is the location where Griptape Nodes will store your static files."""
    console.print(Panel(explainer, expand=False))

    choices, table = _get_griptape_cloud_bucket_ids_and_display_table()

    # This should not be possible
    if len(choices) < 1:
        msg = "No Griptape Cloud Buckets found!"
        raise RuntimeError(msg)

    console.print(table)

    while True:
        try:
            storage_backend_bucket_id = Prompt.ask(
                "Storage Backend Bucket ID",
                default=default_storage_backend_bucket_id,
                show_default=True,
                choices=choices,
            )
            if storage_backend_bucket_id:
                break
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error reading config file: {e}[/bold red]")

    return storage_backend_bucket_id


def _prompt_for_advanced_media_library(*, default_prompt_for_advanced_media_library: bool | None = None) -> bool:
    """Prompts the user whether to register the advanced media library."""
    if default_prompt_for_advanced_media_library is None:
        default_prompt_for_advanced_media_library = False
    explainer = """[bold cyan]Advanced Media Library[/bold cyan]
    Would you like to install the Griptape Nodes Advanced Media Library?
    This node library makes advanced media generation and manipulation nodes available.
    For example, nodes are available for Flux AI image upscaling, or to leverage CUDA for GPU-accelerated image generation.
    CAVEAT: Installing this library requires additional dependencies to download and install, which can take several minutes.
    The Griptape Nodes Advanced Media Library can be added later by following instructions here: [bold blue][link=https://docs.griptapenodes.com]https://docs.griptapenodes.com[/link][/bold blue].
    """
    console.print(Panel(explainer, expand=False))

    return Confirm.ask("Register Advanced Media Library?", default=default_prompt_for_advanced_media_library)


def __build_libraries_list(*, register_advanced_library: bool) -> list[str]:
    """Builds the list of libraries to register based on the advanced library setting."""
    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/929
    libraries_key = "app_events.on_app_initialization_complete.libraries_to_register"
    library_base_dir = xdg_data_home() / "griptape_nodes/libraries"

    current_libraries = config_manager.get_config_value(
        libraries_key,
        config_source="user_config",
        default=config_manager.get_config_value(libraries_key, config_source="default_config", default=[]),
    )
    new_libraries = current_libraries

    default_library = str(library_base_dir / "griptape_nodes_library/griptape_nodes_library.json")
    # If somehow the user removed the default library, add it back
    if default_library not in current_libraries:
        current_libraries.append(default_library)

    advanced_media_library = str(
        library_base_dir / "griptape_nodes_advanced_media_library/griptape_nodes_advanced_media_library.json"
    )
    if register_advanced_library:
        # If the advanced media library is not registered, add it
        if advanced_media_library not in current_libraries:
            new_libraries.append(advanced_media_library)
    else:  # noqa: PLR5501 easier to reason about this way
        # If the advanced media library is registered, remove it
        if advanced_media_library in current_libraries:
            new_libraries.remove(advanced_media_library)

    return new_libraries


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
            interactive=not args.no_interactive,
            workspace_directory=args.workspace_directory,
            api_key=args.api_key,
            storage_backend=args.storage_backend,
            storage_backend_bucket_id=args.storage_backend_bucket_id,
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
