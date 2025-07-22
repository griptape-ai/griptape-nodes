"""Manages workflow file synchronization.

Provides explicit synchronization capabilities to upload/download
workflow files between workspace and storage backend.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.retained_mode.events.workflow_events import (
    LoadWorkflowMetadata,
    LoadWorkflowMetadataResultSuccess,
    RegisterWorkflowRequest,
    RegisterWorkflowResultSuccess,
    SyncDownWorkflowsRequest,
    SyncDownWorkflowsResultFailure,
    SyncDownWorkflowsResultSuccess,
    SyncUpWorkflowsRequest,
    SyncUpWorkflowsResultFailure,
    SyncUpWorkflowsResultSuccess,
)
from griptape_nodes.retained_mode.utilities.storage import StorageUtility

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager


logger = logging.getLogger("griptape_nodes")


class SyncManager:
    """Manages workflow file synchronization."""

    def __init__(
        self,
        config_manager: ConfigManager,
        secrets_manager: SecretsManager,
        event_manager: EventManager | None = None,
    ) -> None:
        """Initialize the SyncManager.

        Args:
            config_manager: The ConfigManager instance to get workspace directory and storage config.
            secrets_manager: The SecretsManager for accessing storage secrets.
            event_manager: The EventManager instance to use for event handling.
        """
        self._event_manager = event_manager
        self._workspace_path = Path(str(config_manager.workspace_path))

        bucket_id = secrets_manager.get_secret("GT_CLOUD_BUCKET_ID")
        api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY")

        if not bucket_id:
            logger.warning("GT_CLOUD_BUCKET_ID secret not found - sync functionality will be disabled")
            self._storage_utility = None
        else:
            workflows_directory = config_manager.get_config_value("workflows_directory", default="workflows")

            storage_driver = GriptapeCloudStorageDriver(
                bucket_id=bucket_id,
                api_key=api_key,
                working_dir=workflows_directory,
            )

            self._storage_utility = StorageUtility(storage_driver)

        # Register event handlers
        if self._event_manager:
            self._event_manager.assign_manager_to_request_type(
                SyncUpWorkflowsRequest, self.on_sync_up_workflows_request
            )
            self._event_manager.assign_manager_to_request_type(
                SyncDownWorkflowsRequest, self.on_sync_down_workflows_request
            )

    def on_sync_up_workflows_request(
        self, _request: SyncUpWorkflowsRequest
    ) -> SyncUpWorkflowsResultSuccess | SyncUpWorkflowsResultFailure:
        """Handle sync up workflows request - upload all workflow files to storage backend.

        Args:
            request: The sync up workflows request

        Returns:
            Success or failure result
        """
        if self._storage_utility is None:
            error_msg = "Attempted to sync up workflows from local workspace to Griptape Cloud. Failed because GT_CLOUD_BUCKET_ID is not configured"
            logger.error(error_msg)
            return SyncUpWorkflowsResultFailure(exception=Exception(error_msg))

        try:
            self._sync_up_workflows(self._storage_utility)
            logger.info("Successfully synced up workflows from local storage to Griptape Cloud")
            return SyncUpWorkflowsResultSuccess()
        except Exception as e:
            error_msg = f"Attempted to sync up workflows from local storage to Griptape Cloud. Failed because: {e}"
            logger.error(error_msg)
            return SyncUpWorkflowsResultFailure(exception=Exception(error_msg))

    def on_sync_down_workflows_request(
        self, _request: SyncDownWorkflowsRequest
    ) -> SyncDownWorkflowsResultSuccess | SyncDownWorkflowsResultFailure:
        """Handle sync down workflows request - download workflow files from storage backend.

        Args:
            request: The sync down workflows request

        Returns:
            Success or failure result
        """
        if self._storage_utility is None:
            error_msg = "Attempted to sync down workflows from Griptape Cloud to local workspace. Failed because GT_CLOUD_BUCKET_ID is not configured"
            logger.error(error_msg)
            return SyncDownWorkflowsResultFailure(exception=Exception(error_msg))

        try:
            self._sync_down_workflows(self._storage_utility)
            logger.info("Successfully synced down workflows from Griptape Cloud to local workspace")
            return SyncDownWorkflowsResultSuccess()
        except Exception as e:
            error_msg = f"Attempted to sync down workflows from Griptape Cloud to local workspace. Failed because: {e}"
            logger.error(error_msg)
            return SyncDownWorkflowsResultFailure(exception=Exception(error_msg))

    def _sync_up_workflows(self, storage_utility: StorageUtility) -> None:
        """Upload all workflow files from workspace to storage backend."""
        try:
            # Find all .py files in the workspace
            py_files = list(self._workspace_path.rglob("*.py"))

            if not py_files:
                return

            # Kick off uploads and return immediately
            self._upload_files(storage_utility, py_files, self._workspace_path)

        except Exception as e:
            logger.error("Failed to scan workspace for workflow files: %s", e)
            raise

    def _upload_single_file(self, storage_utility: StorageUtility, file_path: Path, workspace_path: Path) -> None:
        """Upload a single file synchronously.

        Args:
            storage_utility: Storage utility instance for uploading files
            file_path: Path to the file to upload
            workspace_path: Base workspace path for relative path calculation
        """
        try:
            # Get relative path from workspace
            relative_path = file_path.relative_to(workspace_path)
            file_name = str(relative_path)

            # Read file content
            file_content = file_path.read_bytes()

            # Upload file using storage utility
            storage_utility.save_static_file(file_content, file_name)
            logger.debug("Uploaded workflow file: %s", file_name)

        except Exception as e:
            logger.error("Failed to upload workflow file %s: %s", file_path, e)

    def _upload_files(self, storage_utility: StorageUtility, py_files: list[Path], workspace_path: Path) -> None:
        """Kick off file uploads using thread pool without waiting for results.

        Args:
            storage_utility: Storage utility instance for uploading files
            py_files: List of file paths to upload
            workspace_path: Base workspace path for relative path calculation
        """
        # Use thread pool to run uploads concurrently without waiting
        executor = ThreadPoolExecutor()
        for file_path in py_files:
            executor.submit(self._upload_single_file, storage_utility, file_path, workspace_path)

    def _sync_down_workflows(self, storage_utility: StorageUtility) -> None:
        """Download workflow files from storage backend to workspace."""
        logger.info("Listing all available files from storage...")
        file_names = storage_utility.list_files()
        if not file_names:
            logger.warning("No files found in storage to sync down")
            return

        logger.info("Starting sync down of %d workflow files: %s", len(file_names), file_names)

        self._workspace_path.mkdir(parents=True, exist_ok=True)

        # Kick off downloads and return immediately
        self._download_files(storage_utility, file_names, self._workspace_path)

        # Register downloaded workflows so they become available in the registry
        logger.info("Registering %d downloaded workflow files...", len(file_names))
        self._register_downloaded_workflows(file_names)

    def _download_single_file(self, storage_utility: StorageUtility, file_name: str, workspace_path: Path) -> None:
        """Download a single file synchronously.

        Args:
            storage_utility: Storage utility instance for downloading files
            file_name: Name of the file to download
            workspace_path: Base workspace path for file writing
        """
        try:
            # Download file content using storage utility
            file_content = storage_utility.get_static_file(file_name)

            # Write to workspace
            file_path = workspace_path / file_name
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_bytes(file_content)

            logger.debug("Downloaded workflow file: %s", file_name)

        except Exception as e:
            logger.error("Failed to download workflow file %s: %s", file_name, e)

    def _download_files(self, storage_utility: StorageUtility, file_names: list[str], workspace_path: Path) -> None:
        """Kick off file downloads using thread pool without waiting for results.

        Args:
            storage_utility: Storage utility instance for downloading files
            file_names: List of file names to download
            workspace_path: Base workspace path for file writing
        """
        # Use thread pool to run downloads concurrently without waiting
        executor = ThreadPoolExecutor()
        for file_name in file_names:
            executor.submit(self._download_single_file, storage_utility, file_name, workspace_path)

    def _register_downloaded_workflows(self, file_names: list[str]) -> None:
        """Register downloaded workflow files so they become available in the workflow registry.

        Args:
            file_names: List of workflow file names that were downloaded
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        registered_count = 0
        failed_count = 0

        for file_name in file_names:
            try:
                # Step 1: Load workflow metadata from file
                load_metadata_request = LoadWorkflowMetadata(file_name=file_name)
                load_metadata_result = GriptapeNodes.handle_request(load_metadata_request)

                if not isinstance(load_metadata_result, LoadWorkflowMetadataResultSuccess):
                    logger.warning("Failed to load metadata for workflow file: %s", file_name)
                    failed_count += 1
                    continue

                # Step 2: Register the workflow using the loaded metadata
                register_request = RegisterWorkflowRequest(metadata=load_metadata_result.metadata, file_name=file_name)
                register_result = GriptapeNodes.handle_request(register_request)

                if isinstance(register_result, RegisterWorkflowResultSuccess):
                    logger.info(
                        "Successfully registered workflow '%s' from file: %s", register_result.workflow_name, file_name
                    )
                    registered_count += 1
                else:
                    logger.warning("Failed to register workflow from file: %s", file_name)
                    failed_count += 1

            except Exception as e:
                logger.error("Error registering workflow from file %s: %s", file_name, e)
                failed_count += 1

        if registered_count > 0:
            logger.info("Successfully registered %d workflows", registered_count)
        if failed_count > 0:
            logger.warning("Failed to register %d workflows", failed_count)
