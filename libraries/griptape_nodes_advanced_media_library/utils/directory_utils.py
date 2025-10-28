"""Directory utilities for the advanced media library."""

import logging

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")


def check_cleanup_intermediates_directory() -> None:
    """Check if directory cleanup is enabled and perform cleanup if needed.

    This function checks the configuration to see if directory cleanup is enabled
    for the advanced media library. If enabled, it will clean up the intermediates
    directory by removing the oldest files until the directory size is below the
    configured maximum size threshold.

    The function uses the following configuration values:
    - advanced_media_library.enable_directory_cleanup: Boolean to enable/disable cleanup
    - advanced_media_library.max_directory_size_gb: Maximum directory size in GB
    - advanced_media_library.temp_folder_name: Name of the intermediates directory
    - static_files_directory: Base directory for static files

    Note:
        This function is typically called before saving new intermediate files
        to ensure sufficient space is available.
    """
    # Perform cleanup if needed before saving new file
    cleanup_enabled = GriptapeNodes.ConfigManager().get_config_value("advanced_media_library.enable_directory_cleanup")
    if cleanup_enabled:
        static_files_directory = GriptapeNodes.ConfigManager().get_config_value("static_files_directory")
        intermediates_directory = get_intermediates_directory_path()
        path = GriptapeNodes.ConfigManager().workspace_path / static_files_directory / intermediates_directory

        max_size_gb = GriptapeNodes.ConfigManager().get_config_value("advanced_media_library.max_directory_size_gb")
        GriptapeNodes.OSManager().cleanup_directory_if_needed(full_directory_path=path, max_size_gb=max_size_gb)


def get_intermediates_directory_path() -> str:
    """Get the configured intermediates directory name for the advanced media library.

    This function retrieves the directory name where intermediate files (such as
    preview images during AI generation) are stored. The directory name is
    configured via the 'advanced_media_library.temp_folder_name' setting.

    Returns:
        str: The configured intermediates directory name, or "intermediates" if not configured.
            This is a directory name (not a full path) that will be used relative to
            the static files directory.

    Note:
        If the configuration value is not found, a warning is logged and the default
        "intermediates" directory name is returned.
    """
    # Get configured temp folder name, default to "intermediates"
    temp_folder_name = GriptapeNodes.ConfigManager().get_config_value("advanced_media_library.temp_folder_name")
    if temp_folder_name is None:
        logger.warning(
            "Configuration value 'advanced_media_library.temp_folder_name' not found, using default 'intermediates'"
        )
        temp_folder_name = "intermediates"
    return temp_folder_name
