from __future__ import annotations

import logging
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.sync_events import (
    ListCloudWorkflowsRequest,
    ListCloudWorkflowsResultFailure,
    ListCloudWorkflowsResultSuccess,
    StartSyncAllCloudWorkflowsRequest,
    StartSyncAllCloudWorkflowsResultFailure,
    StartSyncAllCloudWorkflowsResultSuccess,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager


logger = logging.getLogger("griptape_nodes")


class WorkflowFileHandler(FileSystemEventHandler):
    """Handles file system events for workflow files in the synced directory."""

    def __init__(self, sync_manager: SyncManager) -> None:
        super().__init__()
        self.sync_manager = sync_manager

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if not event.is_directory and str(event.src_path).endswith(".py"):
            logger.info("Detected modification of workflow file: %s", event.src_path)
            self.sync_manager._upload_workflow_file(Path(str(event.src_path)))

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if not event.is_directory and str(event.src_path).endswith(".py"):
            logger.info("Detected creation of workflow file: %s", event.src_path)
            self.sync_manager._upload_workflow_file(Path(str(event.src_path)))

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events."""
        if not event.is_directory and str(event.src_path).endswith(".py"):
            logger.info("Detected deletion of workflow file: %s", event.src_path)
            self.sync_manager._delete_workflow_file(Path(str(event.src_path)))


class SyncManager:
    """Manager for syncing workflows with cloud storage."""

    SYNCED_WORKFLOWS_DIR = "synced_workflows"

    def __init__(self, event_manager: EventManager) -> None:
        self._active_sync_tasks: dict[str, threading.Thread] = {}
        self._observer: Observer | None = None  # pyright: ignore[reportInvalidTypeForm]
        self._file_handler: WorkflowFileHandler | None = None

        event_manager.assign_manager_to_request_type(
            StartSyncAllCloudWorkflowsRequest,
            self.on_start_sync_all_cloud_workflows_request,
        )
        event_manager.assign_manager_to_request_type(
            ListCloudWorkflowsRequest,
            self.on_list_cloud_workflows_request,
        )

        event_manager.add_listener_to_app_event(
            AppInitializationComplete,
            self.on_app_initialization_complete,
        )

    def _get_cloud_storage_driver(self) -> GriptapeCloudStorageDriver:
        """Get configured cloud storage driver.

        Returns:
            Configured GriptapeCloudStorageDriver instance.

        Raises:
            RuntimeError: If required cloud configuration is missing.
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        secrets_manager = GriptapeNodes.SecretsManager()

        # Get cloud storage configuration from secrets
        bucket_id = secrets_manager.get_secret("GT_CLOUD_BUCKET_ID")
        base_url = secrets_manager.get_secret("GT_CLOUD_BASE_URL", should_error_on_not_found=False)
        api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY")

        if not bucket_id:
            msg = "Cloud storage bucket_id not configured. Set GT_CLOUD_BUCKET_ID secret."
            raise RuntimeError(msg)
        if not api_key:
            msg = "Cloud storage api_key not configured. Set GT_CLOUD_API_KEY secret."
            raise RuntimeError(msg)

        return GriptapeCloudStorageDriver(
            bucket_id=bucket_id,
            base_url=base_url,
            api_key=api_key,
            static_files_directory="synced_workflows",
        )

    def _get_sync_directory(self) -> Path:
        """Get the local sync directory path, creating it if it doesn't exist.

        Returns:
            Path to the synced_workflows directory.
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        config_manager = GriptapeNodes.ConfigManager()
        sync_dir = config_manager.workspace_path / self.SYNCED_WORKFLOWS_DIR

        # Create directory if it doesn't exist
        sync_dir.mkdir(parents=True, exist_ok=True)

        return sync_dir

    def _download_cloud_workflow_to_sync_dir(self, filename: str) -> bool:
        """Download a workflow file from cloud storage to the sync directory.

        Args:
            filename: Name of the workflow file to download from cloud

        Returns:
            True if download was successful, False otherwise
        """
        try:
            storage_driver = self._get_cloud_storage_driver()
            sync_dir = self._get_sync_directory()

            # Download file content from cloud
            file_content = storage_driver.download_file(filename)

            # Write to local sync directory
            local_file_path = sync_dir / filename
            with local_file_path.open("wb") as f:
                f.write(file_content)

            logger.info("Successfully downloaded cloud workflow to sync directory: %s", filename)
        except Exception as e:
            logger.error("Failed to download cloud workflow '%s': %s", filename, str(e))
            return False
        else:
            return True

    def _get_workflow_name_from_path(self, file_path: Path) -> str | None:
        """Extract workflow name from file path.

        Args:
            file_path: Path to the workflow file

        Returns:
            Workflow name without .py extension, or None if not valid
        """
        if not file_path.name.endswith(".py"):
            return None
        return file_path.stem

    def _check_workflow_sync_status(self, workflow_name: str, file_path: Path) -> bool:  # noqa: ARG002
        """Check sync status between local and cloud workflow versions.

        Args:
            workflow_name: Name of the workflow
            file_path: Path to the local workflow file

        Returns:
            True if should proceed with upload, False if cloud version was downloaded instead
        """
        # Simplified: always proceed with upload for now
        # Cloud comparison logic removed as requested
        logger.debug("Workflow sync check for '%s': proceeding with upload.", workflow_name)
        return True

    def _upload_workflow_file(self, file_path: Path) -> None:
        """Upload a single workflow file to cloud storage.

        Args:
            file_path: Path to the workflow file to upload.
        """
        try:
            # Get workflow name from file path
            workflow_name = self._get_workflow_name_from_path(file_path)
            if not workflow_name:
                logger.error("Invalid workflow file path: %s", file_path)
                return

            # Check sync status and download cloud version if newer
            if not self._check_workflow_sync_status(workflow_name, file_path):
                return

            # Proceed with upload
            storage_driver = self._get_cloud_storage_driver()

            # Read file content
            with file_path.open("rb") as f:
                file_content = f.read()

            # Upload to cloud storage using signed URL pattern
            filename = file_path.name
            response = storage_driver.create_signed_upload_url(filename)

            # Upload the file using the signed URL
            upload_response = httpx.request(
                response["method"],
                response["url"],
                content=file_content,
                headers=response["headers"],
            )
            upload_response.raise_for_status()

            logger.info("Successfully uploaded workflow file to cloud: %s", filename)

        except Exception as e:
            logger.error("Failed to upload workflow file '%s': %s", file_path.name, str(e))

    def _delete_workflow_file(self, file_path: Path) -> None:
        """Delete a workflow file from cloud storage.

        Args:
            file_path: Path to the workflow file that was deleted locally.
        """
        try:
            storage_driver = self._get_cloud_storage_driver()
            filename = file_path.name

            # Use the storage driver's delete method
            storage_driver.delete_file(filename)
            logger.info("Successfully deleted workflow file from cloud: %s", filename)

        except Exception as e:
            logger.error("Failed to delete workflow file '%s' from cloud: %s", file_path.name, str(e))

    def _start_file_watching(self) -> None:
        """Start watching the synced_workflows directory for changes."""
        try:
            sync_dir = self._get_sync_directory()

            # Create file handler and observer
            self._file_handler = WorkflowFileHandler(self)
            self._observer = Observer()

            # Schedule and start the observer
            self._observer.schedule(self._file_handler, str(sync_dir), recursive=False)  # type: ignore[union-attr]
            self._observer.start()  # type: ignore[union-attr]

            logger.info("Started watching synced workflows directory: %s", sync_dir)

        except Exception as e:
            logger.error("Failed to start file watching: %s", str(e))

    def _stop_file_watching(self) -> None:
        """Stop watching the synced_workflows directory."""
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join()
            logger.info("Stopped watching synced workflows directory")

        self._observer = None
        self._file_handler = None

    def on_list_cloud_workflows_request(self, _request: ListCloudWorkflowsRequest) -> ResultPayload:
        """List all workflow files available in cloud storage."""
        try:
            storage_driver = self._get_cloud_storage_driver()

            # List all assets in the bucket
            all_assets = storage_driver.list_assets()

            # Filter for Python workflow files
            workflow_files = []
            for asset in all_assets:
                asset_name = asset.get("name", "")
                if asset_name.endswith(".py"):
                    workflow_files.append(
                        {
                            "name": asset_name,
                            "size": asset.get("size", 0),
                            "last_modified": asset.get("last_modified"),
                            "created_at": asset.get("created_at"),
                        }
                    )

            logger.info("Found %d workflow files in cloud storage", len(workflow_files))
            return ListCloudWorkflowsResultSuccess(workflows=workflow_files)

        except Exception as e:
            logger.error("Failed to list cloud workflows: %s", str(e))
            return ListCloudWorkflowsResultFailure()

    def on_start_sync_all_cloud_workflows_request(self, _request: StartSyncAllCloudWorkflowsRequest) -> ResultPayload:
        """Start syncing all cloud workflows to local synced_workflows directory."""
        try:
            storage_driver = self._get_cloud_storage_driver()
            sync_dir = self._get_sync_directory()

            # List all assets in the bucket to get count
            all_assets = storage_driver.list_assets()
            workflow_files = [asset for asset in all_assets if asset.get("name", "").endswith(".py")]

            if not workflow_files:
                logger.info("No workflow files found in cloud storage")
                return StartSyncAllCloudWorkflowsResultSuccess(sync_directory=str(sync_dir), total_workflows=0)

            # Start background sync with unique ID
            sync_task_id = str(uuid.uuid4())
            sync_thread = threading.Thread(
                target=self._sync_workflows_background,
                args=(sync_task_id, workflow_files, storage_driver, sync_dir),
                name=f"SyncWorkflows-{sync_task_id}",
                daemon=True,
            )

            self._active_sync_tasks[sync_task_id] = sync_thread
            sync_thread.start()

            logger.info("Started background sync for %d workflow files", len(workflow_files))
            return StartSyncAllCloudWorkflowsResultSuccess(
                sync_directory=str(sync_dir), total_workflows=len(workflow_files)
            )

        except Exception as e:
            logger.error("Failed to start cloud workflow sync: %s", str(e))
            return StartSyncAllCloudWorkflowsResultFailure()

    def _sync_workflows_background(
        self, sync_id: str, workflow_files: list[dict], storage_driver: GriptapeCloudStorageDriver, sync_dir: Path
    ) -> None:
        """Background thread function to sync workflows."""
        synced_workflows = []
        failed_downloads = []
        total_workflows = len(workflow_files)

        logger.info("Starting background sync of %d workflows (sync_id: %s)", total_workflows, sync_id)

        for asset in workflow_files:
            file_name = asset.get("name", "")
            try:
                # Download file content
                file_content = storage_driver.download_file(file_name)

                # Extract just the filename (remove any directory prefixes)
                local_filename = Path(file_name).name
                local_file_path = sync_dir / local_filename

                # Write to local file
                with local_file_path.open("wb") as f:
                    f.write(file_content)

                synced_workflows.append(local_filename)
                logger.debug("Successfully synced workflow: %s", local_filename)

            except Exception as e:
                logger.warning("Failed to sync workflow '%s': %s", file_name, str(e))
                failed_downloads.append(file_name)

        if failed_downloads:
            logger.warning("Failed to sync %d workflows: %s", len(failed_downloads), failed_downloads)

        logger.info(
            "Background sync completed: %d of %d workflows synced to %s (sync_id: %s)",
            len(synced_workflows),
            len(workflow_files),
            sync_dir,
            sync_id,
        )

        # Clean up task tracking
        if sync_id in self._active_sync_tasks:
            del self._active_sync_tasks[sync_id]

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        """Automatically start syncing cloud workflows when the app initializes."""
        try:
            # Check if cloud storage is configured before attempting sync
            self._get_cloud_storage_driver()

            logger.info("App initialization complete - starting automatic cloud workflow sync")

            # Create and handle the sync request
            sync_request = StartSyncAllCloudWorkflowsRequest()

            # Use handle_request to process through normal event system
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            result = GriptapeNodes.handle_request(sync_request)

            if isinstance(result, StartSyncAllCloudWorkflowsResultSuccess):
                logger.info(
                    "Automatic cloud workflow sync started successfully - %d workflows will be synced to %s",
                    result.total_workflows,
                    result.sync_directory,
                )

                # Start file watching after successful sync
                self._start_file_watching()
            else:
                logger.debug("Automatic cloud workflow sync failed to start (likely cloud not configured)")

        except Exception as e:
            logger.debug("Automatic cloud workflow sync skipped: %s", str(e))

    def cleanup(self) -> None:
        """Clean up resources when shutting down."""
        self._stop_file_watching()
