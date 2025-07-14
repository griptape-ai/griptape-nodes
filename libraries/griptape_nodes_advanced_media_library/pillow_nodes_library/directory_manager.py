import logging
from pathlib import Path

logger = logging.getLogger("pillow_nodes_library")


class DirectoryManager:
    """Utility class for managing directory size and cleaning up old files."""

    @staticmethod
    def cleanup_directory_if_needed(directory_path: str) -> bool:
        """Check directory size and cleanup old files if needed.

        Args:
            directory_path: Path to the directory to check and clean

        Returns:
            True if cleanup was performed, False otherwise
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        config_manager = GriptapeNodes.ConfigManager()

        # Get configuration values
        max_size_mb = config_manager.get_config_value("advanced_media_library.max_directory_size_mb")
        cleanup_enabled = config_manager.get_config_value("advanced_media_library.enable_directory_cleanup")

        # Default values if not configured
        if max_size_mb is None:
            max_size_mb = 1000  # 1GB default
        if cleanup_enabled is None:
            cleanup_enabled = True

        if not cleanup_enabled:
            return False

        # Calculate current directory size
        current_size_mb = DirectoryManager._get_directory_size_mb(directory_path)

        if current_size_mb <= max_size_mb:
            return False

        logger.info(
            "Directory %s size (%.1f MB) exceeds limit (%s MB). Starting cleanup...",
            directory_path,
            current_size_mb,
            max_size_mb,
        )

        # Perform cleanup
        return DirectoryManager._cleanup_old_files(directory_path, max_size_mb)

    @staticmethod
    def _get_directory_size_mb(directory_path: str) -> float:
        """Get total size of directory in MB.

        Args:
            directory_path: Path to the directory

        Returns:
            Total size in MB
        """
        total_size = 0
        path = Path(directory_path)

        if not path.exists():
            return 0.0

        for file_path in path.rglob("*"):
            if file_path.is_file():
                try:
                    total_size += file_path.stat().st_size
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    continue

        return total_size / (1024 * 1024)  # Convert to MB

    @staticmethod
    def _cleanup_old_files(directory_path: str, target_size_mb: float) -> bool:
        """Remove oldest files until directory is under target size.

        Args:
            directory_path: Path to the directory to clean
            target_size_mb: Target size in MB

        Returns:
            True if files were removed, False otherwise
        """
        path = Path(directory_path)
        if not path.exists():
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
                    continue

        if not files_with_times:
            return False

        # Sort by modification time (oldest first)
        files_with_times.sort(key=lambda x: x[1])

        # Remove files until we're under the target size
        removed_count = 0
        target_cleanup_size = target_size_mb * 0.8  # Clean to 80% of target to avoid frequent cleanups

        for file_path, _ in files_with_times:
            try:
                file_path.unlink()
                removed_count += 1

                # Check if we're now under the target size
                current_size_mb = DirectoryManager._get_directory_size_mb(directory_path)
                if current_size_mb <= target_cleanup_size:
                    break

            except (OSError, FileNotFoundError):
                # Skip files that can't be deleted
                continue

        if removed_count > 0:
            final_size_mb = DirectoryManager._get_directory_size_mb(directory_path)
            logger.info(
                "Cleaned up %d old files from %s. Directory size reduced to %.1f MB",
                removed_count,
                directory_path,
                final_size_mb,
            )

        return removed_count > 0
