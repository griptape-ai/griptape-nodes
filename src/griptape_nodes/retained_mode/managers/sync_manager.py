"""Manages workflow file synchronization.

Provides explicit synchronization capabilities to upload/download
workflow files between workspace and storage backend.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from griptape.utils.contextvars_utils import with_contextvars

from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.retained_mode.events.workflow_events import (
    LoadWorkflowMetadata,
    LoadWorkflowMetadataResultSuccess,
    RegisterWorkflowRequest,
    RegisterWorkflowResultSuccess,
    StartSyncDownWorkflowsRequest,
    StartSyncDownWorkflowsResultFailure,
    StartSyncDownWorkflowsResultSuccess,
    StartSyncUpWorkflowsRequest,
    StartSyncUpWorkflowsResultFailure,
    StartSyncUpWorkflowsResultSuccess,
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
        self, config_manager: ConfigManager, secrets_manager: SecretsManager, event_manager: EventManager
    ) -> None:
        """Initialize the SyncManager.

        Args:
            config_manager: The ConfigManager instance to get workspace directory and storage config.
            secrets_manager: The SecretsManager for accessing storage secrets.
            event_manager: The EventManager instance to use for event handling.
        """
        self._workspace_path = Path(str(config_manager.workspace_path))

        bucket_id = secrets_manager.get_secret("GT_CLOUD_BUCKET_ID")
        api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY")

        if not bucket_id:
            logger.warning("GT_CLOUD_BUCKET_ID secret not found - sync functionality will be disabled")
            self._storage_utility = None
        else:
            workflows_directory = config_manager.get_config_value("workflows_directory")

            storage_driver = GriptapeCloudStorageDriver(
                bucket_id=bucket_id,
                api_key=api_key,
                working_dir=workflows_directory,
            )

            self._storage_utility = StorageUtility(storage_driver)

        # Register event handlers
        event_manager.assign_manager_to_request_type(StartSyncUpWorkflowsRequest, self.on_sync_up_workflows_request)
        event_manager.assign_manager_to_request_type(StartSyncDownWorkflowsRequest, self.on_sync_down_workflows_request)

    def on_sync_up_workflows_request(
        self, _request: StartSyncUpWorkflowsRequest
    ) -> StartSyncUpWorkflowsResultSuccess | StartSyncUpWorkflowsResultFailure:
        """Handle sync up workflows request - upload all workflow files to storage backend.

        Args:
            request: The sync up workflows request

        Returns:
            Success or failure result
        """
        if self._storage_utility is None:
            error_msg = "Attempted to sync up workflows from local workspace to Griptape Cloud. Failed because GT_CLOUD_BUCKET_ID is not configured"
            logger.error(error_msg)
            return StartSyncUpWorkflowsResultFailure(exception=Exception(error_msg))

        try:
            self._sync_up_workflows(self._storage_utility)
            logger.info("Successfully synced up workflows from local storage to Griptape Cloud")
            return StartSyncUpWorkflowsResultSuccess()
        except Exception as e:
            error_msg = f"Attempted to sync up workflows from local storage to Griptape Cloud. Failed because: {e}"
            logger.error(error_msg)
            return StartSyncUpWorkflowsResultFailure(exception=Exception(error_msg))

    def on_sync_down_workflows_request(
        self, _request: StartSyncDownWorkflowsRequest
    ) -> StartSyncDownWorkflowsResultSuccess | StartSyncDownWorkflowsResultFailure:
        """Handle sync down workflows request - download workflow files from storage backend.

        Args:
            request: The sync down workflows request

        Returns:
            Success or failure result
        """
        if self._storage_utility is None:
            error_msg = "Attempted to sync down workflows from Griptape Cloud to local workspace. Failed because GT_CLOUD_BUCKET_ID is not configured"
            logger.error(error_msg)
            return StartSyncDownWorkflowsResultFailure(exception=Exception(error_msg))

        try:
            # Kick off sync in background thread and return immediately
            ThreadPoolExecutor().submit(with_contextvars(self._sync_down_workflows), self._storage_utility)
            logger.info("Started syncing down workflows from Griptape Cloud to local workspace")
            return StartSyncDownWorkflowsResultSuccess()
        except Exception as e:
            error_msg = f"Attempted to sync down workflows from Griptape Cloud to local workspace. Failed because: {e}"
            logger.error(error_msg)
            return StartSyncDownWorkflowsResultFailure(exception=Exception(error_msg))

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

    def _upload_workflow(self, storage_utility: StorageUtility, file_path: Path, workspace_path: Path) -> None:
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
            executor.submit(self._upload_workflow, storage_utility, file_path, workspace_path)

    def _sync_down_workflows(self, storage_utility: StorageUtility) -> None:
        """Download workflow files from storage backend to workspace."""
        logger.info("Listing all available files from storage...")
        file_names = storage_utility.list_files()
        if not file_names:
            logger.warning("No files found in storage to sync down")
            return

        logger.info("Starting sync down of %d workflow files: %s", len(file_names), file_names)

        self._workspace_path.mkdir(parents=True, exist_ok=True)

        # Download files and register each workflow as it downloads
        self._download_files(storage_utility, file_names, self._workspace_path)

        logger.info("All workflow files have been downloaded and registered")

    def _download_workflow(self, storage_utility: StorageUtility, file_name: str, workspace_path: Path) -> None:
        """Download a single file synchronously and register it.

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

            # Register the workflow immediately after successful download
            self._register_workflow(file_name)

        except Exception as e:
            logger.error("Failed to download workflow file %s: %s", file_name, e)

    def _download_files(self, storage_utility: StorageUtility, file_names: list[str], workspace_path: Path) -> None:
        """Download files using thread pool and wait for all downloads to complete.

        Args:
            storage_utility: Storage utility instance for downloading files
            file_names: List of file names to download
            workspace_path: Base workspace path for file writing
        """
        # Use thread pool to run downloads concurrently and wait for completion
        with ThreadPoolExecutor() as executor:
            for file_name in file_names:
                executor.submit(with_contextvars(self._download_workflow), storage_utility, file_name, workspace_path)

    def _register_workflow(self, file_name: str) -> None:
        """Register a single downloaded workflow file.

        Args:
            file_name: Name of the workflow file to register
        """
        from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        try:
            # Step 1: Load workflow metadata from file
            load_metadata_request = LoadWorkflowMetadata(file_name=file_name)
            load_metadata_result = GriptapeNodes.handle_request(load_metadata_request)

            if not isinstance(load_metadata_result, LoadWorkflowMetadataResultSuccess):
                logger.warning("Failed to load metadata for workflow file: %s", file_name)
                return

            if WorkflowRegistry.has_workflow_with_name(load_metadata_result.metadata.name):
                return

            # Step 2: Register the workflow using the loaded metadata
            register_request = RegisterWorkflowRequest(metadata=load_metadata_result.metadata, file_name=file_name)
            register_result = GriptapeNodes.handle_request(register_request)

            if isinstance(register_result, RegisterWorkflowResultSuccess):
                logger.info(
                    "Successfully registered workflow '%s' from file: %s", register_result.workflow_name, file_name
                )
            else:
                logger.warning("Failed to register workflow from file: %s", file_name)

        except Exception as e:
            logger.error("Error registering workflow from file %s: %s", file_name, e)
