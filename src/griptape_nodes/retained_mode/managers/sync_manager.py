"""Manages workflow file synchronization using pycrdt.

Tracks changes to workflow files in the workspace and provides CRDT-based
synchronization capabilities for collaborative editing scenarios.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pycrdt
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from griptape_nodes.retained_mode.events.base_events import AppEvent

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

from griptape_nodes.retained_mode.events.app_events import AppWorkflowChanged

logger = logging.getLogger("griptape_nodes")


class WorkflowFileHandler(FileSystemEventHandler):
    """Handles file system events for workflow files."""

    def __init__(self, sync_manager: SyncManager) -> None:
        """Initialize the file handler.

        Args:
            sync_manager: The SyncManager instance to notify of changes
        """
        super().__init__()
        self._sync_manager = sync_manager

    # def on_created(self, event: FileSystemEvent) -> None:
    #     """Handle file creation events."""
    #     if not event.is_directory and str(event.src_path).endswith(".py"):
    #         self._sync_manager._handle_file_creation(Path(str(event.src_path)))

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if not event.is_directory and str(event.src_path).endswith(".py"):
            logger.info("Modified")
            self._sync_manager._handle_file_modification(Path(str(event.src_path)))

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events."""
        if not event.is_directory and str(event.src_path).endswith(".py"):
            self._sync_manager._handle_file_deletion(Path(str(event.src_path)))


class SyncManager:
    """Manages workflow file synchronization using pycrdt."""

    def __init__(self, event_manager: EventManager | None = None, config_manager: ConfigManager | None = None) -> None:
        """Initialize the SyncManager.

        Args:
            event_manager: The EventManager instance to use for event handling.
            config_manager: The ConfigManager instance to get workspace directory.
        """
        if config_manager is None:
            msg = "ConfigManager is required for SyncManager"
            raise ValueError(msg)

        self._event_manager = event_manager
        self._workflow_docs: dict[str, pycrdt.Doc] = {}
        self._workspace_path: str = str(config_manager.workspace_path)

        if event_manager is not None:
            event_manager.add_listener_to_app_event(AppWorkflowChanged, self.on_app_workflow_changed)

        self._start_file_watcher()
        self._track_existing_files()

    def _handle_workflow_changes(self, workflow_name: str, event: pycrdt.TransactionEvent) -> None:
        """Handle changes to a specific workflow.

        Args:
            workflow_name: Name of the workflow that changed
            event: pycrdt change event
        """
        from griptape_nodes.app.app import event_queue

        app_event = AppWorkflowChanged(workflow_name=workflow_name, update_bytes=event.update)
        event_queue.put(AppEvent(payload=app_event, topic="app-event"))

    def on_app_workflow_changed(self, event: AppWorkflowChanged) -> None:
        """Handle AppWorkflowChanged events.

        This handler is called when a workflow change event is broadcast.
        Applies remote updates to the local document and saves to disk.

        Args:
            event: The AppWorkflowChanged event containing workflow name and update bytes
        """
        logger.info("Applying remote workflow update for %s", event.workflow_name)
        workflow_name = event.workflow_name
        update_bytes = event.update_bytes
        print(type(update_bytes))
        print(update_bytes)

        remote_doc = self._workflow_docs[workflow_name]
        remote_doc.apply_update(update_bytes)

        # Get the updated content and save to disk
        workflow_text = remote_doc["workflow"]["content"]
        updated_content = str(workflow_text)

        # Find the file path and save
        workspace_path = Path(self._workspace_path)
        file_path = workspace_path / workflow_name

        if file_path.exists():
            file_path.write_text(updated_content)
            logger.info("Applied remote update and saved workflow: %s", workflow_name)
        else:
            logger.warning("Workflow file not found for saving: %s", file_path)

    def _start_file_watcher(self) -> None:
        """Start watching the workspace directory for file changes."""
        workspace_path = Path(self._workspace_path)
        if not workspace_path.exists():
            logger.warning("Workspace directory does not exist: %s", self._workspace_path)
            return

        try:
            self._observer = Observer()
            event_handler = WorkflowFileHandler(self)
            self._observer.schedule(event_handler, self._workspace_path, recursive=True)
            self._observer.start()
        except Exception as e:
            logger.error(
                "Failed to start file system watcher for workspace %s: %s",
                self._workspace_path,
                e,
            )

    def _stop_file_watcher(self) -> None:
        """Stop watching the workspace directory for file changes."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            logger.info("Stopped file system watcher for workspace: %s", self._workspace_path)
            self._observer = None

    def _track_existing_files(self) -> None:
        """Initialize tracking for existing files in the workspace."""
        workspace_path = Path(self._workspace_path)

        try:
            # Find all .py files in the workspace
            py_files = list(workspace_path.rglob("*.py"))
            logger.info("Found %d Python files to initialize tracking for", len(py_files))

            for py_file in py_files:
                self._handle_file_creation(py_file)
        except Exception as e:
            logger.error("Failed to initialize existing files: %s", e)

    def _handle_file_creation(self, file_path: Path) -> None:
        """Handle file creation by creating a new CRDT document.

        Args:
            file_path: Path to the created file
        """
        try:
            workflow_name = file_path.name
            if workflow_name in self._workflow_docs:
                logger.warning("Workflow %s is already being tracked, treating as modification", workflow_name)
                self._handle_file_modification(file_path)
                return

            # If already tracking, treat as modification instead
            if workflow_name in self._workflow_docs:
                self._handle_file_modification(file_path)
                return

            workflow_content = file_path.read_text()

            # Create a new doc for this workflow
            doc = pycrdt.Doc()

            doc["workflow"] = pycrdt.Map({"content": workflow_content})

            # Store the doc
            self._workflow_docs[workflow_name] = doc

            # Set up change observer for this workflow
            doc.observe(lambda event: self._handle_workflow_changes(workflow_name, event))

            logger.info("Started tracking workflow: %s (path: %s)", workflow_name, file_path)
        except Exception as e:
            logger.error("Failed to handle file creation for %s: %s", file_path, e)

    def _handle_file_modification(self, file_path: Path) -> None:
        """Handle file modification by updating existing CRDT document.

        Args:
            file_path: Path to the modified file
        """
        try:
            workflow_name = file_path.name

            # If not tracking, treat as creation instead
            if workflow_name not in self._workflow_docs:
                self._handle_file_creation(file_path)
                return

            workflow_content = file_path.read_text()

            # Get existing content from CRDT doc to compare
            doc = self._workflow_docs[workflow_name]
            existing_content = str(doc["workflow"]["content"])

            # Only update if content has actually changed
            if workflow_content != existing_content:
                doc["workflow"] = pycrdt.Map({"content": workflow_content})
            else:
                logger.debug("Skipping update for %s - content unchanged", workflow_name)

        except Exception as e:
            logger.error("Failed to handle file modification for %s: %s", file_path, e)

    def _handle_file_deletion(self, file_path: Path) -> None:
        """Handle file deletion events.

        Args:
            file_path: Path to the deleted file
        """
        workflow_name = file_path.name
        if workflow_name in self._workflow_docs:
            del self._workflow_docs[workflow_name]
