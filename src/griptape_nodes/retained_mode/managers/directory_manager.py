import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager

logger = logging.getLogger("griptape_nodes")


class DirectoryManager:
    """Manager for directory size management and cleanup operations."""

    def __init__(self, config_manager: "ConfigManager") -> None:
        """Initialize the DirectoryManager.

        Args:
            config_manager: The ConfigManager instance to use for accessing configuration.
        """
        self.config_manager = config_manager

    def cleanup_directory_if_needed(self, directory_path: str, config_prefix: str = "advanced_media_library") -> bool:
        """Check directory size and cleanup old files if needed.

        Args:
            directory_path: Path to the directory to check and clean
            config_prefix: Configuration prefix for the library (e.g., "advanced_media_library")

        Returns:
            True if cleanup was performed, False otherwise
        """
        # Get configuration values with library prefix
        max_size_gb = self.config_manager.get_config_value(f"{config_prefix}.max_directory_size_gb")
        cleanup_enabled = self.config_manager.get_config_value(f"{config_prefix}.enable_directory_cleanup")

        # Default values if not configured
        if max_size_gb is None:
            max_size_gb = 1  # 1GB default
        if cleanup_enabled is None:
            cleanup_enabled = False

        if not cleanup_enabled:
            return False

        # Calculate current directory size
        current_size_gb = self._get_directory_size_gb(directory_path)

        if current_size_gb <= max_size_gb:
            return False

        logger.info(
            "Directory %s size (%.1f GB) exceeds limit (%s GB). Starting cleanup...",
            directory_path,
            current_size_gb,
            max_size_gb,
        )

        # Perform cleanup
        return self._cleanup_old_files(directory_path, max_size_gb)

    def _get_directory_size_gb(self, directory_path: str) -> float:
        """Get total size of directory in GB.

        Args:
            directory_path: Path to the directory

        Returns:
            Total size in GB
        """
        total_size = 0
        static_files_directory = self.config_manager.get_config_value("static_files_directory", default="staticfiles")
        path = Path(self.config_manager.workspace_path / static_files_directory / directory_path)

        if not path.exists():
            return 0.0

        for _, _, files in os.walk(path):
            for f in files:
                fp = path / f
                if not fp.is_symlink():
                    total_size += fp.stat().st_size
        return total_size / (1024 * 1024 * 1024)  # Convert to GB

    def _cleanup_old_files(self, directory_path: str, target_size_gb: float) -> bool:
        """Remove oldest files until directory is under target size.

        Args:
            directory_path: Path to the directory to clean
            target_size_gb: Target size in GB

        Returns:
            True if files were removed, False otherwise
        """
        static_files_directory = self.config_manager.get_config_value("static_files_directory", default="staticfiles")
        path = self.config_manager.workspace_path / static_files_directory / directory_path
        if not path.exists():
            logger.error("Directory %s does not exist. Skipping cleanup.", path)
            return False

        # Get all files with their modification times
        files_with_times: list[tuple[Path, float]] = []

        for file_path in path.rglob("*"):
            if file_path.is_file():
                try:
                    mtime = file_path.stat().st_mtime
                    files_with_times.append((file_path, mtime))
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    logger.error("Could not dele file %s. Skipping this file.", file_path)
                    continue

        if not files_with_times:
            return False

        # Sort by modification time (oldest first)
        files_with_times.sort(key=lambda x: x[1])

        # Remove files until we're under the target size
        removed_count = 0

        for file_path, _ in files_with_times:
            try:
                file_path.unlink()
                removed_count += 1

                # Check if we're now under the target size
                current_size_gb = self._get_directory_size_gb(directory_path)
                if current_size_gb <= target_size_gb:
                    break

            except (OSError, FileNotFoundError):
                # Skip files that can't be deleted
                logger.error("Could not delete file %s. Skipping this file.", file_path)

        if removed_count > 0:
            final_size_gb = self._get_directory_size_gb(directory_path)
            logger.info(
                "Cleaned up %d old files from %s. Directory size reduced to %.1f GB",
                removed_count,
                directory_path,
                final_size_gb,
            )

        return removed_count > 0
