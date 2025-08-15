"""Griptape Nodes package."""

from rich.console import Console

console = Console()

with console.status("Loading Griptape Nodes...") as status:
    import argparse
    import json
    import os
    import shutil
    import sys
    import tarfile
    import tempfile
    from dataclasses import dataclass
    from pathlib import Path
    from typing import Any

    import httpx
    from rich.box import HEAVY_EDGE
    from rich.panel import Panel
    from rich.progress import Progress
    from rich.prompt import Confirm, Prompt
    from rich.table import Table
    from xdg_base_dirs import xdg_config_home, xdg_data_home

    from griptape_nodes.app import start_app
    from griptape_nodes.drivers.storage import StorageBackend
    from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.os_manager import OSManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
    from griptape_nodes.utils.uv_utils import find_uv_bin
    from griptape_nodes.utils.version_utils import (
        get_complete_version_string,
        get_current_version,
        get_install_source,
        get_latest_version_git,
        get_latest_version_pypi,
    )

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
ENV_REGISTER_ADVANCED_LIBRARY = (
    os.getenv("GTN_REGISTER_ADVANCED_LIBRARY", "false").lower() == "true"
    if os.getenv("GTN_REGISTER_ADVANCED_LIBRARY") is not None
    else None
)
ENV_LIBRARIES_SYNC = (
    os.getenv("GTN_LIBRARIES_SYNC", "false").lower() == "true" if os.getenv("GTN_LIBRARIES_SYNC") is not None else None
)
ENV_GTN_BUCKET_NAME = os.getenv("GTN_BUCKET_NAME")
ENV_LIBRARIES_BASE_DIR = os.getenv("GTN_LIBRARIES_BASE_DIR", str(DATA_DIR / "libraries"))


@dataclass
class InitConfig:
    """Configuration for initialization."""

    interactive: bool = True
    workspace_directory: str | None = None
    api_key: str | None = None
    storage_backend: str | None = None
    register_advanced_library: bool | None = None
    config_values: dict[str, Any] | None = None
    secret_values: dict[str, str] | None = None
    libraries_sync: bool | None = None
    bucket_name: str | None = None


config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)
os_manager = OSManager()


def main() -> None:
    """Main entry point for the Griptape Nodes CLI."""
    # Hack to make paths "just work". # noqa: FIX004
    # Without this, packages like `nodes` don't properly import.
    # Long term solution could be to make `nodes` a proper src-layout package
    # but current engine relies on importing files rather than packages.
    sys.path.append(str(Path.cwd()))

    args = _get_args()
    _process_args(args)


def _run_init(config: InitConfig) -> None:
    """Runs through the engine init steps.

    Args:
        config: Initialization configuration.
    """
    __init_system_config()

    # Run configuration flow
    _run_init_configuration(config)

    # Sync libraries
    if config.libraries_sync is not False:
        _sync_libraries()

    console.print("[bold green]Initialization complete![/bold green]")


def _handle_api_key_config(config: InitConfig) -> str | None:
    """Handle API key configuration step."""
    api_key = config.api_key

    if config.interactive:
        api_key = _prompt_for_api_key(default_api_key=api_key)

    if api_key is not None:
        secrets_manager.set_secret("GT_CLOUD_API_KEY", api_key)
        console.print("[bold green]Griptape API Key set")

    return api_key


def _handle_workspace_config(config: InitConfig) -> str | None:
    """Handle workspace directory configuration step."""
    workspace_directory = config.workspace_directory

    if config.interactive:
        workspace_directory = _prompt_for_workspace(default_workspace_directory=workspace_directory)

    if workspace_directory is not None:
        config_manager.set_config_value("workspace_directory", workspace_directory)
        console.print(f"[bold green]Workspace directory set to: {workspace_directory}[/bold green]")

    return workspace_directory


def _handle_storage_backend_config(config: InitConfig) -> str | None:
    """Handle storage backend configuration step."""
    storage_backend = config.storage_backend

    if config.interactive:
        storage_backend = _prompt_for_storage_backend(default_storage_backend=storage_backend)

    if storage_backend is not None:
        config_manager.set_config_value("storage_backend", storage_backend)
        console.print(f"[bold green]Storage backend set to: {storage_backend}")

    return storage_backend


def _handle_bucket_config(config: InitConfig) -> str | None:
    """Handle bucket configuration step (depends on API key)."""
    bucket_id = None

    if config.interactive:
        # First ask if they want to configure a bucket
        configure_bucket = _prompt_for_bucket_configuration()
        if configure_bucket:
            bucket_id = _prompt_for_gtc_bucket_name(default_bucket_name=config.bucket_name)
    elif config.bucket_name is not None:
        bucket_id = _get_or_create_bucket_id(config.bucket_name)

    if bucket_id is not None:
        secrets_manager.set_secret("GT_CLOUD_BUCKET_ID", bucket_id)
        console.print(f"[bold green]Bucket ID set to: {bucket_id}[/bold green]")

    return bucket_id


def _handle_advanced_library_config(config: InitConfig) -> bool | None:
    """Handle advanced library configuration step."""
    register_advanced_library = config.register_advanced_library

    if config.interactive:
        register_advanced_library = _prompt_for_advanced_media_library(
            default_prompt_for_advanced_media_library=register_advanced_library
        )

    if register_advanced_library is not None:
        libraries_to_register = __build_libraries_list(register_advanced_library=register_advanced_library)
        config_manager.set_config_value(
            "app_events.on_app_initialization_complete.libraries_to_register", libraries_to_register
        )
        console.print(f"[bold green]Libraries to register set to: {', '.join(libraries_to_register)}[/bold green]")

    return register_advanced_library


def _handle_arbitrary_configs(config: InitConfig) -> None:
    """Handle arbitrary config and secret values."""
    # Set arbitrary config values
    if config.config_values:
        for key, value in config.config_values.items():
            config_manager.set_config_value(key, value)
            console.print(f"[bold green]Config '{key}' set to: {value}[/bold green]")

    # Set arbitrary secret values
    if config.secret_values:
        for key, value in config.secret_values.items():
            secrets_manager.set_secret(key, value)
            console.print(f"[bold green]Secret '{key}' set[/bold green]")


def _run_init_configuration(config: InitConfig) -> None:
    """Handle initialization with proper dependency ordering."""
    _handle_api_key_config(config)

    _handle_workspace_config(config)

    _handle_storage_backend_config(config)

    _handle_bucket_config(config)

    _handle_advanced_library_config(config)

    _handle_arbitrary_configs(config)


def _start_engine(*, no_update: bool = False) -> None:
    """Starts the Griptape Nodes engine.

    Args:
        no_update (bool): If True, skips the auto-update check.
    """
    if not CONFIG_DIR.exists():
        # Default init flow if there is no config directory
        console.print("[bold green]Config directory not found. Initializing...[/bold green]")
        _run_init(
            InitConfig(
                workspace_directory=ENV_WORKSPACE_DIRECTORY,
                api_key=ENV_API_KEY,
                storage_backend=ENV_STORAGE_BACKEND,
                register_advanced_library=ENV_REGISTER_ADVANCED_LIBRARY,
                interactive=True,
                config_values=None,
                secret_values=None,
                libraries_sync=ENV_LIBRARIES_SYNC,
                bucket_name=ENV_GTN_BUCKET_NAME,
            )
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
        choices=list(StorageBackend),
        default=ENV_STORAGE_BACKEND,
    )
    init_parser.add_argument(
        "--bucket-name",
        help="Name for the bucket (existing or new) when using 'gtc' storage backend.",
        default=ENV_GTN_BUCKET_NAME,
    )
    init_parser.add_argument(
        "--register-advanced-library",
        help="Install the Griptape Nodes Advanced Image Library.",
        default=ENV_REGISTER_ADVANCED_LIBRARY,
    )
    init_parser.add_argument(
        "--libraries-sync",
        help="Sync the Griptape Nodes libraries.",
        default=ENV_LIBRARIES_SYNC,
    )
    init_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Run init in non-interactive mode (no prompts).",
    )
    init_parser.add_argument(
        "--config",
        action="append",
        metavar="KEY=VALUE",
        help="Set arbitrary config values as key=value pairs (can be used multiple times). Example: --config log_level=DEBUG --config workspace_directory=/tmp",
    )
    init_parser.add_argument(
        "--secret",
        action="append",
        metavar="KEY=VALUE",
        help="Set arbitrary secret values as key=value pairs (can be used multiple times). Example: --secret MY_API_KEY=abc123 --secret OTHER_KEY=xyz789",
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
    config_show_parser = config_subparsers.add_parser("show", help="Show configuration values.")
    config_show_parser.add_argument(
        "config_path",
        nargs="?",
        help="Optional config path to show specific value (e.g., 'workspace_directory').",
    )
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

    # libraries
    libraries_parser = subparsers.add_parser("libraries", help="Manage local libraries.")
    libraries_subparsers = libraries_parser.add_subparsers(
        dest="subcommand",
        metavar="SUBCOMMAND",
        required=True,
    )
    libraries_subparsers.add_parser("sync", help="Sync libraries with your current engine version.")

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
                choices=list(StorageBackend),
                default=default_storage_backend,
                show_default=True,
            )
            if storage_backend:
                break
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error reading config file: {e}[/bold red]")

    return storage_backend


def _get_griptape_cloud_buckets_and_display_table() -> tuple[list[str], dict[str, str], Table]:
    """Fetches the list of Griptape Cloud Buckets from the API.

    Returns:
        tuple: (bucket_names, name_to_id_mapping, display_table)
    """
    api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY")
    bucket_names: list[str] = []
    name_to_id: dict[str, str] = {}

    if api_key is None:
        msg = "Griptape Cloud API Key not found."
        raise RuntimeError(msg)

    table = Table(show_header=True, box=HEAVY_EDGE, show_lines=True, expand=True)
    table.add_column("Bucket Name", style="green")
    table.add_column("Bucket ID", style="green")

    try:
        buckets = GriptapeCloudStorageDriver.list_buckets(base_url=GT_CLOUD_BASE_URL, api_key=api_key)
        for bucket in buckets:
            bucket_name = bucket["name"]
            bucket_id = bucket["bucket_id"]
            bucket_names.append(bucket_name)
            name_to_id[bucket_name] = bucket_id
            table.add_row(bucket_name, bucket_id)
    except RuntimeError as e:
        console.print(f"[red]Error fetching buckets: {e}[/red]")

    return bucket_names, name_to_id, table


def _prompt_for_bucket_configuration() -> bool:
    """Prompts the user whether to configure a bucket for multi-machine workflow and asset syncing."""
    # Check if there's already a bucket configured
    current_bucket_id = secrets_manager.get_secret("GT_CLOUD_BUCKET_ID", should_error_on_not_found=False)

    if current_bucket_id:
        explainer = f"""[bold cyan]Griptape Cloud Bucket Configuration[/bold cyan]
    You currently have a bucket configured (ID: {current_bucket_id}).

    Buckets are used for multi-machine workflow and asset syncing, allowing you to:
    - Share workflows and assets across multiple devices
    - Sync generated content between different Griptape Nodes instances
    - Access your work from anywhere

    Would you like to change your selected bucket or keep the current one?"""
        prompt_text = "Change selected Griptape Cloud bucket?"
        default_value = False
    else:
        explainer = """[bold cyan]Griptape Cloud Bucket Configuration[/bold cyan]
    Would you like to configure a Griptape Cloud bucket?
    Buckets are used for multi-machine workflow and asset syncing, allowing you to:
    - Share workflows and assets across multiple devices
    - Sync generated content between different Griptape Nodes instances
    - Access your work from anywhere

    If you do not intend to use Griptape Nodes to collaborate or revision control your workflows, you can skip this step.

    You can always configure a bucket later by running the initialization process again."""
        prompt_text = "Configure Griptape Cloud bucket?"
        default_value = False

    console.print(Panel(explainer, expand=False))
    return Confirm.ask(prompt_text, default=default_value)


def _prompt_for_gtc_bucket_name(default_bucket_name: str | None = None) -> str:
    """Prompts the user for a GTC bucket and returns the bucket ID."""
    explainer = """[bold cyan]Storage Backend Bucket Selection[/bold cyan]
Select a Griptape Cloud Bucket to use for storage. This is the location where Griptape Nodes will store your static files."""
    console.print(Panel(explainer, expand=False))

    # Fetch existing buckets
    bucket_names, name_to_id, table = _get_griptape_cloud_buckets_and_display_table()
    if default_bucket_name is None:
        # Default to "default" bucket if it exists
        default_bucket_name = "default" if "default" in name_to_id else None

    # Display existing buckets if any
    if len(bucket_names) > 0:
        console.print(table)
        console.print("\n[dim]You can enter an existing bucket by name, or enter a new name to create one.[/dim]")

    while True:
        # Prompt user for bucket name
        selected_bucket_name = Prompt.ask(
            "Enter bucket name",
            default=default_bucket_name,
            show_default=bool(default_bucket_name),
        )

        if selected_bucket_name:
            # Check if it's an existing bucket
            if selected_bucket_name in name_to_id:
                return name_to_id[selected_bucket_name]
            # It's a new bucket name, confirm creation
            create_bucket = Confirm.ask(
                f"Bucket '{selected_bucket_name}' doesn't exist. Create it?",
                default=True,
            )
            if create_bucket:
                return __create_new_bucket(selected_bucket_name)
                # If they don't want to create, continue the loop to ask again


def _get_or_create_bucket_id(bucket_name: str) -> str:
    """Gets the bucket ID for an existing bucket or creates a new one.

    Args:
        bucket_name: Name of the bucket to lookup or create

    Returns:
        The bucket ID
    """
    # Fetch existing buckets to check if bucket_name exists
    _, name_to_id, _ = _get_griptape_cloud_buckets_and_display_table()

    # Check if bucket already exists
    if bucket_name in name_to_id:
        return name_to_id[bucket_name]

    # Create the bucket
    return __create_new_bucket(bucket_name)


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
    library_base_dir = Path(ENV_LIBRARIES_BASE_DIR)

    current_libraries = config_manager.get_config_value(
        libraries_key,
        config_source="user_config",
        default=config_manager.get_config_value(libraries_key, config_source="default_config", default=[]),
    )
    new_libraries = current_libraries.copy()

    def _get_library_identifier(library_path: str) -> str:
        """Get the unique identifier for a library based on parent/filename."""
        path = Path(library_path)
        return f"{path.parent.name}/{path.name}"

    # Create a set of current library identifiers for fast lookup
    current_identifiers = {_get_library_identifier(lib) for lib in current_libraries}

    default_library = str(library_base_dir / "griptape_nodes_library/griptape_nodes_library.json")
    default_identifier = _get_library_identifier(default_library)
    # If somehow the user removed the default library, add it back
    if default_identifier not in current_identifiers:
        new_libraries.append(default_library)

    advanced_media_library = str(library_base_dir / "griptape_nodes_advanced_media_library/griptape_nodes_library.json")
    advanced_identifier = _get_library_identifier(advanced_media_library)
    if register_advanced_library:
        # If the advanced media library is not registered, add it
        if advanced_identifier not in current_identifiers:
            new_libraries.append(advanced_media_library)
    else:
        # If the advanced media library is registered, remove it
        libraries_to_remove = [lib for lib in new_libraries if _get_library_identifier(lib) == advanced_identifier]
        for lib in libraries_to_remove:
            new_libraries.remove(lib)

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
        return get_latest_version_pypi(package, PYPI_UPDATE_URL)
    if install_source == "git":
        return get_latest_version_git(package, GITHUB_UPDATE_URL, LATEST_TAG)
    # If the package is installed from a file, just return the current version since the user is likely managing it manually
    return get_current_version()


def _auto_update_self() -> None:
    """Automatically updates the script to the latest version if the user confirms."""
    console.print("[bold green]Checking for updates...[/bold green]")
    source, commit_id = get_install_source()
    current_version = get_current_version()
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
    """Installs the latest release of the CLI *and* refreshes bundled libraries."""
    console.print("[bold green]Starting updater...[/bold green]")

    os_manager.replace_process([sys.executable, "-m", "griptape_nodes.updater"])


def _sync_libraries() -> None:
    """Download and sync Griptape Nodes libraries, copying only directories from synced libraries."""
    install_source, _ = get_install_source()
    # Unless we're installed from PyPi, grab libraries from the 'latest' tag
    if install_source == "pypi":
        version = get_current_version()
    else:
        version = LATEST_TAG

    console.print(f"[bold cyan]Fetching Griptape Nodes libraries ({version})...[/bold cyan]")

    tar_url = NODES_TARBALL_URL.format(tag=version)
    console.print(f"[green]Downloading from {tar_url}[/green]")
    dest_nodes = Path(ENV_LIBRARIES_BASE_DIR)

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "nodes.tar.gz"

        # Streaming download with a tiny progress bar
        with httpx.stream("GET", tar_url, follow_redirects=True) as r, Progress() as progress:
            task = progress.add_task("[green]Downloading...", total=int(r.headers.get("Content-Length", 0)))
            progress.start()
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                console.print(f"[red]Error fetching libraries: {e}[/red]")
                return
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

        # Copy directories from synced libraries without removing existing content
        console.print(f"[green]Syncing libraries to {dest_nodes.resolve()}...[/green]")
        dest_nodes.mkdir(parents=True, exist_ok=True)
        for library_dir in extracted_libs.iterdir():
            if library_dir.is_dir():
                dest_library_dir = dest_nodes / library_dir.name
                if dest_library_dir.exists():
                    shutil.rmtree(dest_library_dir)
                shutil.copytree(library_dir, dest_library_dir)
                console.print(f"[green]Synced library: {library_dir.name}[/green]")

    # Re-initialize all libraries from config
    console.print("[bold cyan]Initializing libraries...[/bold cyan]")
    try:
        GriptapeNodes.LibraryManager().load_all_libraries_from_config()
        console.print("[bold green]Libraries Initialized successfully.[/bold green]")
    except Exception as e:
        console.print(f"[red]Error initializing libraries: {e}[/red]")

    console.print("[bold green]Libraries synced.[/bold green]")


def _print_current_version() -> None:
    """Prints the current version of the script."""
    version_string = get_complete_version_string()
    console.print(f"[bold green]{version_string}[/bold green]")


def _print_user_config(config_path: str | None = None) -> None:
    """Prints the user configuration from the config file.

    Args:
        config_path: Optional path to specific config value. If None, prints entire config.
    """
    if config_path is None:
        config = config_manager.merged_config
        sys.stdout.write(json.dumps(config, indent=2))
    else:
        try:
            value = config_manager.get_config_value(config_path)
            if isinstance(value, (dict, list)):
                sys.stdout.write(json.dumps(value, indent=2))
            else:
                sys.stdout.write(str(value))
        except (KeyError, AttributeError, ValueError):
            console.print(f"[bold red]Config path '{config_path}' not found[/bold red]")
            sys.exit(1)


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

    # Remove the tool using UV
    uv_path = find_uv_bin()
    os_manager.replace_process([uv_path, "tool", "uninstall", "griptape-nodes"])


def _parse_key_value_pairs(pairs: list[str] | None) -> dict[str, Any] | None:
    """Parse key=value pairs from a list of strings.

    Args:
        pairs: List of strings in the format "key=value"

    Returns:
        Dictionary of key-value pairs, or None if no pairs provided
    """
    if not pairs:
        return None

    result = {}
    for pair in pairs:
        if "=" not in pair:
            console.print(f"[bold red]Invalid key=value pair: {pair}. Expected format: key=value[/bold red]")
            continue
        # Split only on the first = to handle values that contain =
        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            console.print(f"[bold red]Empty key in pair: {pair}[/bold red]")
            continue

        # Try to parse value as JSON, fall back to string if it fails
        try:
            parsed_value = json.loads(value)
            result[key] = parsed_value
        except (json.JSONDecodeError, ValueError):
            # If JSON parsing fails, use the original string value
            result[key] = value

    return result if result else None


def _process_args(args: argparse.Namespace) -> None:  # noqa: C901, PLR0912
    if args.command == "init":
        config_values = _parse_key_value_pairs(getattr(args, "config", None))
        secret_values = _parse_key_value_pairs(getattr(args, "secret", None))

        _run_init(
            InitConfig(
                interactive=not args.no_interactive,
                workspace_directory=args.workspace_directory,
                api_key=args.api_key,
                storage_backend=args.storage_backend,
                register_advanced_library=args.register_advanced_library,
                config_values=config_values,
                secret_values=secret_values,
                libraries_sync=args.libraries_sync,
                bucket_name=args.bucket_name,
            )
        )
    elif args.command == "engine":
        _start_engine(no_update=args.no_update)
    elif args.command == "config":
        if args.subcommand == "list":
            _list_user_configs()
        elif args.subcommand == "reset":
            _reset_user_config()
        elif args.subcommand == "show":
            _print_user_config(args.config_path)
    elif args.command == "self":
        if args.subcommand == "update":
            _update_self()
        elif args.subcommand == "uninstall":
            _uninstall_self()
        elif args.subcommand == "version":
            _print_current_version()
    elif args.command == "libraries":
        if args.subcommand == "sync":
            _sync_libraries()
    else:
        msg = f"Unknown command: {args.command}"
        raise ValueError(msg)


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


def __create_new_bucket(bucket_name: str) -> str:
    """Create a new Griptape Cloud bucket.

    Args:
        bucket_name: Name for the bucket

    Returns:
        The bucket ID of the created bucket.
    """
    api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY")
    if api_key is None:
        msg = "GT_CLOUD_API_KEY secret is required to create a bucket."
        raise ValueError(msg)

    try:
        bucket_id = GriptapeCloudStorageDriver.create_bucket(
            bucket_name=bucket_name, base_url=GT_CLOUD_BASE_URL, api_key=api_key
        )
    except Exception as e:
        console.print(f"[bold red]Failed to create bucket: {e}[/bold red]")
        raise
    else:
        console.print(f"[bold green]Successfully created bucket '{bucket_name}' with ID: {bucket_id}[/bold green]")
        return bucket_id


if __name__ == "__main__":
    main()
