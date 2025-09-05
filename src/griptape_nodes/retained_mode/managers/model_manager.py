import asyncio
import contextlib
import hashlib
import json
import logging
import multiprocessing
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from huggingface_hub import list_models, snapshot_download
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError

try:
    from huggingface_hub.constants import HF_HUB_CACHE
except ImportError:
    from huggingface_hub import HF_HUB_CACHE
from xdg_base_dirs import xdg_data_home

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.model_events import (
    CancelModelDownloadRequest,
    CancelModelDownloadResultFailure,
    CancelModelDownloadResultSuccess,
    DeleteModelRequest,
    DeleteModelResultFailure,
    DeleteModelResultSuccess,
    DownloadModelRequest,
    DownloadModelResultFailure,
    DownloadModelResultSuccess,
    GetModelDownloadStatusRequest,
    GetModelDownloadStatusResultFailure,
    GetModelDownloadStatusResultSuccess,
    ListModelsRequest,
    ListModelsResultFailure,
    ListModelsResultSuccess,
    SearchModelsRequest,
    SearchModelsResultFailure,
    SearchModelsResultSuccess,
)
from griptape_nodes.retained_mode.managers.settings import AppInitializationComplete

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class DownloadCancelledError(Exception):
    """Exception raised when a download is cancelled by the user."""


def download_worker(
    queue: multiprocessing.Queue,
    model_id: str,
    download_kwargs: dict[str, Any],
) -> None:
    """Download worker that runs in a separate process.

    Args:
        queue: Multiprocessing queue for status updates
        model_id: Hugging Face model identifier
        download_kwargs: Parameters for snapshot_download
    """
    try:
        # Emit starting status
        queue.put({"status": "starting", "model_id": model_id, "timestamp": time.time()})

        # Emit downloading status
        queue.put({"status": "downloading", "model_id": model_id, "timestamp": time.time()})

        # Perform the actual download
        local_path = snapshot_download(**download_kwargs)

        # Emit success status
        queue.put({"status": "completed", "model_id": model_id, "local_path": local_path, "timestamp": time.time()})

    except RepositoryNotFoundError:
        queue.put(
            {
                "status": "failed",
                "model_id": model_id,
                "error": f"Repository not found: {model_id}",
                "error_type": "RepositoryNotFoundError",
                "timestamp": time.time(),
            }
        )

    except HfHubHTTPError as e:
        queue.put(
            {
                "status": "failed",
                "model_id": model_id,
                "error": f"HTTP error {e.response.status_code}: {e!s}",
                "error_type": "HfHubHTTPError",
                "timestamp": time.time(),
            }
        )

    except Exception as e:
        queue.put(
            {
                "status": "failed",
                "model_id": model_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": time.time(),
            }
        )


# HTTP status codes
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403

# HuggingFace cache directory parsing constants
MIN_CACHE_DIR_PARTS = 3

# Model download status directory
MODEL_DOWNLOADS_DIR = xdg_data_home() / "griptape_nodes" / "model_downloads"


class SimpleProgressTracker:
    """Simple progress tracker for model downloads that persists status to files."""

    def __init__(self, model_id: str) -> None:
        """Initialize the progress tracker.

        Args:
            model_id: The model identifier being downloaded
        """
        self.model_id = model_id
        self.model_id_hash = self._hash_model_id(model_id)
        self.status_file = MODEL_DOWNLOADS_DIR / f"{self.model_id_hash}.json"
        self.started_at = datetime.now(tz=UTC)

        # Ensure the downloads directory exists
        MODEL_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

        # Initialize status file
        self._write_status("starting")

    def _hash_model_id(self, model_id: str) -> str:
        """Create a safe filename hash from model ID."""
        return hashlib.sha256(model_id.encode()).hexdigest()[:16]

    def _write_status(self, status: str, progress_info: dict | None = None) -> None:
        """Write current progress status to the status file."""
        try:
            status_data = {
                "model_id": self.model_id,
                "status": status,
                "progress_percent": 0.0,
                "downloaded_bytes": 0,
                "total_bytes": 0,
                "started_at": self.started_at.isoformat(),
                "updated_at": datetime.now(tz=UTC).isoformat(),
                "eta_seconds": None,
            }

            # Add progress info if provided
            if progress_info:
                status_data.update(progress_info)

            with self.status_file.open("w", encoding="utf-8") as f:
                json.dump(status_data, f, indent=2)

        except Exception as e:
            logger.warning("Failed to write download status for %s: %s", self.model_id, e)

    def mark_completed(self) -> None:
        """Mark the download as completed and clean up status file."""
        self._write_status("completed")
        self._cleanup_status_file()

    def mark_failed(self, error_message: str) -> None:
        """Mark the download as failed."""
        progress_info = {"error_message": error_message}
        self._write_status("failed", progress_info)

    def mark_cancelled(self) -> None:
        """Mark the download as cancelled and clean up status file."""
        self._write_status("cancelled")
        self._cleanup_status_file()

    def is_cancelled(self) -> bool:
        """Check if the download has been cancelled by reading the status file.

        Returns:
            bool: True if the download has been cancelled, False otherwise
        """
        try:
            if self.status_file.exists():
                with self.status_file.open("r", encoding="utf-8") as f:
                    status_data = json.load(f)
                    return status_data.get("status") == "cancelled"
        except Exception as e:
            logger.warning("Failed to check cancellation status for %s: %s", self.model_id, e)
        return False

    def _cleanup_status_file(self) -> None:
        """Clean up the status file after successful completion."""
        try:
            if self.status_file.exists():
                self.status_file.unlink()
                logger.debug("Cleaned up download status file for %s", self.model_id)
        except Exception as e:
            logger.warning("Failed to clean up status file for %s: %s", self.model_id, e)


class MultiprocessingDownloadManager:
    """Manages model downloads using multiprocessing for clean cancellation."""

    def __init__(self) -> None:
        self.process = None
        self.queue = None
        self.progress_tracker = None

    def start_download(
        self,
        model_id: str,
        download_kwargs: dict[str, Any],
    ) -> None:
        """Start a download in a separate process.

        Args:
            model_id: Hugging Face model identifier
            download_kwargs: Parameters for snapshot_download
        """
        if self.process and self.process.is_alive():
            msg = "Download already in progress"
            raise RuntimeError(msg)

        # Create progress tracker for status file management
        self.progress_tracker = SimpleProgressTracker(model_id)

        self.queue = multiprocessing.Queue()
        self.process = multiprocessing.Process(target=download_worker, args=(self.queue, model_id, download_kwargs))
        self.process.start()

    def get_status(self, timeout: float = 0.1) -> dict[str, Any] | None:
        """Get the latest status update from the download process.

        Args:
            timeout: Timeout for queue.get() in seconds

        Returns:
            Status dictionary or None if no update available
        """
        if not self.queue:
            return None

        try:
            status = self.queue.get(timeout=timeout)
        except Exception:
            return None

        # Update progress tracker with status from worker process
        if self.progress_tracker and status:
            status_type = status.get("status")
            if status_type == "downloading":
                self.progress_tracker._write_status("downloading")
            elif status_type == "completed":
                self.progress_tracker.mark_completed()
            elif status_type == "failed":
                error_message = status.get("error", "Unknown error")
                self.progress_tracker.mark_failed(error_message)
        return status

    def cancel_download(self, timeout: float = 5.0) -> bool:
        """Cancel the current download by terminating the process.

        Args:
            timeout: Time to wait for graceful termination

        Returns:
            True if successfully cancelled, False if no download was running
        """
        print(self.process)
        if not self.process or not self.process.is_alive():
            return False

        # Mark as cancelled in progress tracker
        if self.progress_tracker:
            self.progress_tracker.mark_cancelled()

        # Terminate the process
        self.process.terminate()

        # Wait for termination with timeout
        self.process.join(timeout=timeout)

        # Force kill if still alive
        if self.process.is_alive():
            self.process.kill()
            self.process.join()

        return True

    def is_downloading(self) -> bool:
        """Check if a download is currently in progress."""
        return self.process is not None and self.process.is_alive()

    def cleanup(self) -> None:
        """Clean up resources."""
        if self.process and self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2.0)
            if self.process.is_alive():
                self.process.kill()
                self.process.join()

        self.process = None
        self.queue = None
        self.progress_tracker = None


def get_download_status(model_id: str) -> dict[str, Any] | None:
    """Get the current download status for a model.

    Args:
        model_id: The model identifier

    Returns:
        dict | None: Status data or None if no download found
    """
    model_id_hash = hashlib.sha256(model_id.encode()).hexdigest()[:16]
    status_file = MODEL_DOWNLOADS_DIR / f"{model_id_hash}.json"

    if not status_file.exists():
        return None

    try:
        with status_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to read download status for %s: %s", model_id, e)
        return None


def list_all_downloads() -> list[dict[str, Any]]:
    """List all download statuses.

    Returns:
        list: List of all download status dictionaries
    """
    downloads = []

    if not MODEL_DOWNLOADS_DIR.exists():
        return downloads

    for status_file in MODEL_DOWNLOADS_DIR.glob("*.json"):
        try:
            with status_file.open("r", encoding="utf-8") as f:
                status_data = json.load(f)
                downloads.append(status_data)
        except Exception as e:
            logger.warning("Failed to read status file %s: %s", status_file, e)

    # Sort by started_at timestamp, most recent first
    downloads.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return downloads


def cleanup_failed_downloads(max_age_hours: int = 24) -> int:
    """Clean up old failed download status files.

    Note: Completed downloads are automatically cleaned up when they finish.

    Args:
        max_age_hours: Maximum age in hours for keeping failed downloads

    Returns:
        int: Number of files cleaned up
    """
    if not MODEL_DOWNLOADS_DIR.exists():
        return 0

    cleaned_count = 0
    cutoff_time = datetime.now(tz=UTC).timestamp() - (max_age_hours * 3600)

    for status_file in MODEL_DOWNLOADS_DIR.glob("*.json"):
        try:
            with status_file.open("r", encoding="utf-8") as f:
                status_data = json.load(f)

            # Only clean up failed downloads (completed ones are auto-cleaned)
            status = status_data.get("status", "")
            if status == "failed":
                updated_at = status_data.get("updated_at", "")
                if updated_at:
                    updated_timestamp = datetime.fromisoformat(updated_at).timestamp()
                    if updated_timestamp < cutoff_time:
                        status_file.unlink()
                        cleaned_count += 1

        except Exception as e:
            logger.warning("Failed to process status file %s during cleanup: %s", status_file, e)

    return cleaned_count


class ModelManager:
    """A manager for downloading models from Hugging Face Hub.

    This manager provides async handlers for downloading models using the Hugging Face Hub API.
    It supports downloading entire model repositories or specific files, with caching and
    local storage management.
    """

    def __init__(self, event_manager: "EventManager | None" = None) -> None:
        """Initialize the ModelManager.

        Args:
            event_manager: The EventManager instance to use for event handling.
        """
        # Store active download managers by model_id
        self.active_downloads: dict[str, MultiprocessingDownloadManager] = {}

        if event_manager is not None:
            # Register our request handlers
            event_manager.assign_manager_to_request_type(DownloadModelRequest, self.on_handle_download_model_request)
            event_manager.assign_manager_to_request_type(ListModelsRequest, self.on_handle_list_models_request)
            event_manager.assign_manager_to_request_type(DeleteModelRequest, self.on_handle_delete_model_request)
            event_manager.assign_manager_to_request_type(
                GetModelDownloadStatusRequest, self.on_handle_get_download_status_request
            )
            event_manager.assign_manager_to_request_type(SearchModelsRequest, self.on_handle_search_models_request)
            event_manager.assign_manager_to_request_type(
                CancelModelDownloadRequest, self.on_handle_cancel_download_request
            )

            # Register for app initialization events
            event_manager.add_listener_to_app_event(
                AppInitializationComplete,
                self.on_app_initialization_complete,
            )

    def _parse_model_id(self, model_input: str) -> str:
        """Parse model ID from either a direct model ID or a Hugging Face URL.

        Args:
            model_input: Either a model ID (e.g., 'microsoft/DialoGPT-medium')
                        or a Hugging Face URL (e.g., 'https://huggingface.co/microsoft/DialoGPT-medium')

        Returns:
            str: The parsed model ID in the format 'namespace/repo_name' or 'repo_name'
        """
        # If it's already a simple model ID (no URL scheme), return as-is
        if not model_input.startswith(("http://", "https://")):
            return model_input

        # Parse the URL
        parsed = urlparse(model_input)

        # Check if it's a Hugging Face URL
        if parsed.netloc in ("huggingface.co", "www.huggingface.co"):
            # Extract the path and remove leading slash
            path = parsed.path.lstrip("/")

            # Remove any trailing parameters or fragments
            # The model ID should be in the format: namespace/repo_name or just repo_name
            model_id_match = re.match(r"^([^/]+/[^/?#]+|[^/?#]+)", path)
            if model_id_match:
                return model_id_match.group(1)

        # If we can't parse it, return the original input and let huggingface_hub handle the error
        return model_input

    async def on_handle_download_model_request(self, request: DownloadModelRequest) -> ResultPayload:
        """Handle model download requests asynchronously.

        This method downloads models from Hugging Face Hub using the provided parameters.
        It supports both model IDs and full URLs, and can download entire repositories
        or specific files based on the patterns provided.

        Args:
            request: The download request containing model ID and options

        Returns:
            ResultPayload: Success result with local path or failure with error details
        """
        # Parse the model ID from potential URL
        parsed_model_id = self._parse_model_id(request.model_id)
        if parsed_model_id != request.model_id:
            logger.debug("Parsed model ID '%s' from URL '%s'", parsed_model_id, request.model_id)

        try:
            # Create download parameters
            download_params = {
                "model_id": parsed_model_id,
                "local_dir": request.local_dir,
                "repo_type": request.repo_type,
                "revision": request.revision,
                "allow_patterns": request.allow_patterns,
                "ignore_patterns": request.ignore_patterns,
            }

            # Run the download in a thread to avoid blocking the event loop
            local_path = await asyncio.to_thread(self._download_model, download_params, parsed_model_id)

            result_details = f"Successfully downloaded model '{parsed_model_id}' to '{local_path}'"

            return DownloadModelResultSuccess(
                local_path=str(local_path),
                model_id=parsed_model_id,
                result_details=result_details,
            )

        except RepositoryNotFoundError as e:
            error_msg = f"Repository not found: {parsed_model_id}. Please check the model ID is correct."
            logger.error(error_msg)
            return DownloadModelResultFailure(
                result_details=f"Failed to download model '{parsed_model_id}': {error_msg}",
                exception=e,
            )

        except HfHubHTTPError as e:
            if e.response.status_code == HTTP_UNAUTHORIZED:
                error_msg = f"Authentication required for model: {request.model_id}. Please set up Hugging Face token."
            elif e.response.status_code == HTTP_FORBIDDEN:
                error_msg = f"Access forbidden for model: {request.model_id}. Check permissions or authentication."
            else:
                error_msg = f"HTTP error {e.response.status_code} while downloading model: {request.model_id}"

            logger.error(error_msg)
            return DownloadModelResultFailure(
                result_details=f"Failed to download model '{request.model_id}': {error_msg}",
                exception=e,
            )

        except RuntimeError as e:
            if "cancelled" in str(e).lower():
                # Download was cancelled by user - this is not an error
                result_details = f"Download cancelled for model '{parsed_model_id}'"
                logger.info(result_details)
                return DownloadModelResultSuccess(
                    local_path="",  # No local path since download was cancelled
                    model_id=parsed_model_id,
                    result_details=result_details,
                )
            # Other runtime errors are actual failures
            error_msg = f"Runtime error downloading model '{request.model_id}': {e}"
            logger.error(error_msg)
            return DownloadModelResultFailure(
                result_details=error_msg,
                exception=e,
            )

        except Exception as e:
            error_msg = f"Unexpected error downloading model '{request.model_id}': {e}"
            logger.exception(error_msg)
            return DownloadModelResultFailure(
                result_details=error_msg,
                exception=e,
            )

    def _download_model(self, download_params: dict[str, str | list[str] | None], model_id: str) -> Path:
        """Model download implementation using multiprocessing.

        Args:
            download_params: Dictionary containing download parameters
            model_id: The model identifier for progress tracking

        Returns:
            Path: Local path where the model was downloaded

        Raises:
            RuntimeError: If download was cancelled or failed
        """
        # Validate parameters and build download kwargs
        download_kwargs = self._build_download_kwargs(download_params)

        # Create and start multiprocessing download manager
        download_manager = MultiprocessingDownloadManager()
        self.active_downloads[model_id] = download_manager

        try:
            download_manager.start_download(model_id, download_kwargs)
            local_path = self._monitor_download_progress(download_manager)
            return Path(local_path)
        except Exception:
            # Clean up the download manager on any error
            download_manager.cleanup()
            raise
        finally:
            # Clean up from active downloads
            self.active_downloads.pop(model_id, None)

    def _monitor_download_progress(self, download_manager: MultiprocessingDownloadManager) -> str:
        """Monitor download progress and handle status updates.

        Args:
            download_manager: The download manager to monitor

        Returns:
            str: Local path where the model was downloaded

        Raises:
            RuntimeError: If download failed or was cancelled
        """
        local_path = None
        while download_manager.is_downloading():
            status = download_manager.get_status(timeout=1.0)
            if status:
                status_type = status.get("status")

                if status_type == "completed":
                    local_path = status.get("local_path")
                    break
                if status_type == "failed":
                    self._handle_download_error(status)

            # Check if process is still alive but not responding
            if not download_manager.is_downloading():
                break

        # Get final status if we didn't get completion status in the loop
        if local_path is None:
            final_status = download_manager.get_status(timeout=5.0)
            if final_status and final_status.get("status") == "completed":
                local_path = final_status.get("local_path")

        if local_path is None:
            msg = "Download completed but no local path was returned"
            raise RuntimeError(msg)

        return local_path

    def _handle_download_error(self, status: dict[str, Any]) -> None:
        """Handle download error by re-raising appropriate exception.

        Args:
            status: Status dictionary containing error information
        """
        error_msg = status.get("error", "Unknown error")
        error_type = status.get("error_type", "Exception")

        if error_type == "RepositoryNotFoundError":
            raise RepositoryNotFoundError(error_msg)
        if error_type == "HfHubHTTPError":
            self._raise_http_error(error_msg)
        raise RuntimeError(error_msg)

    def _raise_http_error(self, error_msg: str) -> None:
        """Create and raise HfHubHTTPError with mock response.

        Args:
            error_msg: Error message containing HTTP status code
        """

        class MockResponse:
            def __init__(self, status_code: int) -> None:
                self.status_code = status_code

        # Extract status code from error message if possible
        status_match = re.search(r"HTTP error (\d+)", error_msg)
        status_code = int(status_match.group(1)) if status_match else 500

        mock_response = MockResponse(status_code)
        error = HfHubHTTPError(error_msg, response=mock_response)
        raise error

    def _build_download_kwargs(self, download_params: dict[str, str | list[str] | None]) -> dict:
        """Build kwargs for snapshot_download with validation.

        Args:
            download_params: Dictionary containing download parameters

        Returns:
            dict: Validated download kwargs for snapshot_download
        """
        param_model_id = download_params["model_id"]
        local_dir = download_params["local_dir"]
        repo_type = download_params["repo_type"]
        revision = download_params["revision"]
        allow_patterns = download_params["allow_patterns"]
        ignore_patterns = download_params["ignore_patterns"]

        # Validate string parameters
        if not isinstance(param_model_id, str):
            msg = "model_id must be a string"
            raise TypeError(msg)
        if repo_type is not None and not isinstance(repo_type, str):
            msg = "repo_type must be a string"
            raise TypeError(msg)
        if revision is not None and not isinstance(revision, str):
            msg = "revision must be a string"
            raise TypeError(msg)

        # Build base kwargs (tqdm is monkey patched for progress tracking)
        download_kwargs: dict[str, Any] = {
            "repo_id": param_model_id,
            "repo_type": repo_type,
            "revision": revision,
        }

        # Add optional parameters
        if local_dir is not None and isinstance(local_dir, str):
            download_kwargs["local_dir"] = local_dir
        if allow_patterns is not None and isinstance(allow_patterns, list):
            download_kwargs["allow_patterns"] = allow_patterns
        if ignore_patterns is not None and isinstance(ignore_patterns, list):
            download_kwargs["ignore_patterns"] = ignore_patterns

        return download_kwargs

    def _handle_download_failure(self, model_id: str, error: Exception) -> None:
        """Handle download failure by marking progress tracker as failed.

        Args:
            model_id: The model identifier
            error: The exception that occurred
        """
        # Create minimal tracker to mark failure
        with contextlib.suppress(Exception):
            progress_tracker = SimpleProgressTracker(model_id)
            progress_tracker.mark_failed(str(error))

    async def on_handle_list_models_request(self, request: ListModelsRequest) -> ResultPayload:  # noqa: ARG002
        """Handle model listing requests asynchronously.

        This method scans the local Hugging Face cache directory to find downloaded models
        and returns information about each model including path, size, and metadata.

        Args:
            request: The list request (no parameters needed)

        Returns:
            ResultPayload: Success result with model list or failure with error details
        """
        try:
            # Get models in a thread to avoid blocking the event loop
            models = await asyncio.to_thread(self._list_models)

            result_details = f"Found {len(models)} cached models"

            return ListModelsResultSuccess(
                models=models,
                result_details=result_details,
            )

        except Exception as e:
            error_msg = f"Failed to list models: {e}"
            logger.exception(error_msg)
            return ListModelsResultFailure(
                result_details=error_msg,
                exception=e,
            )

    async def on_handle_delete_model_request(self, request: DeleteModelRequest) -> ResultPayload:
        """Handle model deletion requests asynchronously.

        This method removes a model from the local Hugging Face cache directory.
        It attempts to find and delete the model directory based on the model ID.

        Args:
            request: The delete request containing model_id

        Returns:
            ResultPayload: Success result with deletion confirmation or failure with error details
        """
        # Parse the model ID from potential URL
        parsed_model_id = self._parse_model_id(request.model_id)
        if parsed_model_id != request.model_id:
            logger.debug("Parsed model ID '%s' from URL '%s'", parsed_model_id, request.model_id)

        try:
            # Delete model in a thread to avoid blocking the event loop
            deleted_path = await asyncio.to_thread(self._delete_model, parsed_model_id)

            result_details = f"Successfully deleted model '{parsed_model_id}' from '{deleted_path}'"

            return DeleteModelResultSuccess(
                model_id=parsed_model_id,
                deleted_path=deleted_path,
                result_details=result_details,
            )

        except FileNotFoundError:
            # Even if model isn't found in cache, try to cleanup any orphaned status file
            try:
                await asyncio.to_thread(self._cleanup_download_status, parsed_model_id)
            except Exception as cleanup_error:
                logger.warning("Failed to cleanup status during failed delete: %s", cleanup_error)

            error_msg = f"Model '{parsed_model_id}' not found in local cache"
            logger.warning(error_msg)
            return DeleteModelResultFailure(
                result_details=error_msg,
                exception=FileNotFoundError(error_msg),
            )

        except Exception as e:
            error_msg = f"Failed to delete model '{parsed_model_id}': {e}"
            logger.exception(error_msg)
            return DeleteModelResultFailure(
                result_details=error_msg,
                exception=e,
            )

    async def on_handle_get_download_status_request(self, request: GetModelDownloadStatusRequest) -> ResultPayload:
        """Handle download status requests asynchronously.

        This method retrieves download status for a specific model or all downloads
        from the status files written by the progress tracker.

        Args:
            request: The status request containing optional model_id

        Returns:
            ResultPayload: Success result with status data or failure with error details
        """
        # Parse the model ID from potential URL if provided
        parsed_model_id = self._parse_model_id(request.model_id) if request.model_id else None
        if parsed_model_id and parsed_model_id != request.model_id:
            logger.debug("Parsed model ID '%s' from URL '%s'", parsed_model_id, request.model_id)

        try:
            # Get status in a thread to avoid blocking the event loop
            downloads = await asyncio.to_thread(self._get_download_status, parsed_model_id)

            result_details = f"Retrieved status for {len(downloads)} download(s)"

            return GetModelDownloadStatusResultSuccess(
                downloads=downloads,
                result_details=result_details,
            )

        except Exception as e:
            error_msg = f"Failed to get download status: {e}"
            logger.exception(error_msg)
            return GetModelDownloadStatusResultFailure(
                result_details=error_msg,
                exception=e,
            )

    def _list_models(self) -> list[dict[str, str | int | float]]:
        """Synchronous model listing implementation.

        Scans the Hugging Face cache directory to find downloaded models.

        Returns:
            list[dict]: List of model information dictionaries
        """
        models = []
        cache_path = Path(str(HF_HUB_CACHE))

        if not cache_path.exists():
            return models

        # Scan the cache directory for model repositories
        for model_dir in cache_path.iterdir():
            if model_dir.is_dir() and not model_dir.name.startswith("."):
                # Skip system directories like .locks
                model_info = self._get_model_info(model_dir)
                if model_info:
                    models.append(model_info)

        return models

    def _delete_model(self, model_id: str) -> str:
        """Synchronous model deletion implementation.

        Removes a model from the Hugging Face cache directory.

        Args:
            model_id: The model ID to delete

        Returns:
            str: The path that was deleted

        Raises:
            FileNotFoundError: If the model is not found in cache
        """
        cache_path = Path(str(HF_HUB_CACHE))

        # Convert model_id to cache directory format
        # HuggingFace cache uses "--" to separate org/model parts
        cache_model_name = model_id.replace("/", "--")

        # Look for the model directory
        model_path = None
        for model_dir in cache_path.iterdir():
            if model_dir.is_dir() and model_dir.name.startswith(f"models--{cache_model_name}"):
                model_path = model_dir
                break

        if model_path is None or not model_path.exists():
            error_msg = f"Model '{model_id}' not found in cache directory '{cache_path}'"
            raise FileNotFoundError(error_msg)

        # Remove the entire model directory
        shutil.rmtree(model_path)

        # Also remove any associated download status file
        self._cleanup_download_status(model_id)

        return str(model_path)

    def _cleanup_download_status(self, model_id: str) -> None:
        """Clean up download status file for a model.

        Args:
            model_id: The model ID to clean up status for
        """
        try:
            # Use the same hashing logic as SimpleProgressTracker
            model_id_hash = hashlib.sha256(model_id.encode()).hexdigest()[:16]
            status_file = MODEL_DOWNLOADS_DIR / f"{model_id_hash}.json"

            if status_file.exists():
                status_file.unlink()
        except Exception as e:
            # Log but don't fail the deletion if status cleanup fails
            logger.warning("Failed to cleanup download status for model %s: %s", model_id, e)

    def _get_model_info(self, model_dir: Path) -> dict[str, str | int | float] | None:
        """Get information about a cached model.

        Args:
            model_dir: Path to the model directory in cache

        Returns:
            dict | None: Model information or None if not a valid model directory
        """
        try:
            # Extract model_id from directory name
            # HuggingFace cache format: models--{org}--{model}--{hash}
            dir_name = model_dir.name
            if not dir_name.startswith("models--"):
                return None

            # Parse the model ID from the directory name
            parts = dir_name.split("--")
            if len(parts) >= MIN_CACHE_DIR_PARTS:
                # Reconstruct model_id as org/model
                model_id = f"{parts[1]}/{parts[2]}"
            else:
                model_id = dir_name[8:]  # Remove "models--" prefix

            # Calculate directory size
            total_size = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file())

            return {
                "model_id": model_id,
                "local_path": str(model_dir),
                "size_bytes": total_size,
                "size_mb": round(total_size / (1024 * 1024), 2),
            }

        except Exception:
            # If we can't parse the directory, skip it
            return None

    def _get_download_status(self, model_id: str | None) -> list[dict[str, Any]]:
        """Get download status for a model or all downloads.

        Args:
            model_id: Optional model identifier to get status for

        Returns:
            list[dict]: List of download status dictionaries
        """
        if model_id is not None:
            # Get status for specific model
            status = get_download_status(model_id)
            return [status] if status else []

        # Get all download statuses
        return list_all_downloads()

    async def on_handle_search_models_request(self, request: SearchModelsRequest) -> ResultPayload:
        """Handle model search requests asynchronously.

        This method searches for models on Hugging Face Hub using the provided parameters.
        It supports filtering by query, task, library, author, and tags.

        Args:
            request: The search request containing search parameters

        Returns:
            ResultPayload: Success result with model list or failure with error details
        """
        try:
            # Search models in a thread to avoid blocking the event loop
            search_results = await asyncio.to_thread(self._search_models, request)

            result_details = f"Found {len(search_results['models'])} models"

            return SearchModelsResultSuccess(
                models=search_results["models"],
                total_results=search_results["total_results"],
                query_info=search_results["query_info"],
                result_details=result_details,
            )

        except Exception as e:
            error_msg = f"Failed to search models: {e}"
            logger.exception(error_msg)
            return SearchModelsResultFailure(
                result_details=error_msg,
                exception=e,
            )

    async def on_handle_cancel_download_request(self, request: CancelModelDownloadRequest) -> ResultPayload:
        """Handle model download cancellation requests asynchronously.

        This method cancels an active model download by terminating the download process
        and updating the download status appropriately.

        Args:
            request: The cancel request containing model_id to cancel

        Returns:
            ResultPayload: Success result with cancellation status or failure with error details
        """
        # Parse the model ID from potential URL
        parsed_model_id = self._parse_model_id(request.model_id)
        if parsed_model_id != request.model_id:
            logger.debug("Parsed model ID '%s' from URL '%s'", parsed_model_id, request.model_id)

        try:
            # Check if we have an active download manager for this model
            download_manager = self.active_downloads.get(parsed_model_id)

            if download_manager and download_manager.is_downloading():
                # Cancel the active download process
                was_cancelled = download_manager.cancel_download()

                if was_cancelled:
                    result_details = f"Successfully cancelled active download of '{parsed_model_id}'"
                    logger.info(result_details)

                    # Clean up from active downloads
                    self.active_downloads.pop(parsed_model_id, None)

                    return CancelModelDownloadResultSuccess(
                        model_id=parsed_model_id,
                        was_cancelled=True,
                        result_details=result_details,
                    )
                return CancelModelDownloadResultFailure(
                    result_details=f"Failed to cancel download process for '{parsed_model_id}'",
                )
            # Check the status file to see if download was already completed/failed
            status = get_download_status(parsed_model_id)

            if status:
                status_str = status.get("status", "unknown")

                if status_str in ["completed", "failed", "cancelled"]:
                    return CancelModelDownloadResultSuccess(
                        model_id=parsed_model_id,
                        was_cancelled=False,
                        result_details=f"Download for '{parsed_model_id}' was already {status_str}",
                    )
                # Mark as cancelled in status file for orphaned downloads
                model_id_hash = hashlib.sha256(parsed_model_id.encode()).hexdigest()[:16]
                status_file = MODEL_DOWNLOADS_DIR / f"{model_id_hash}.json"

                try:
                    status["status"] = "cancelled"
                    status["updated_at"] = datetime.now(tz=UTC).isoformat()
                    with status_file.open("w", encoding="utf-8") as f:
                        json.dump(status, f, indent=2)

                    return CancelModelDownloadResultSuccess(
                        model_id=parsed_model_id,
                        was_cancelled=True,
                        result_details=f"Marked orphaned download as cancelled for '{parsed_model_id}'",
                    )
                except Exception as file_error:
                    msg = f"Failed to update status file: {file_error}"
                    raise RuntimeError(msg) from file_error
            else:
                # No download found
                return CancelModelDownloadResultFailure(
                    result_details=f"No download found for '{parsed_model_id}'",
                )

        except Exception as e:
            error_msg = f"Failed to cancel download for '{parsed_model_id}': {e}"
            logger.exception(error_msg)
            return CancelModelDownloadResultFailure(
                result_details=error_msg,
                exception=e,
            )

    def _search_models(self, request: SearchModelsRequest) -> dict[str, Any]:
        """Synchronous model search implementation.

        Searches for models on Hugging Face Hub using the huggingface_hub API.

        Args:
            request: The search request parameters

        Returns:
            dict: Dictionary containing models list, total results, and query info
        """
        # Build search parameters
        search_params = {}

        if request.query:
            search_params["search"] = request.query
        if request.task:
            search_params["task"] = request.task
        if request.library:
            search_params["library"] = request.library
        if request.author:
            search_params["author"] = request.author
        if request.tags:
            search_params["tags"] = request.tags

        # Validate and set sort parameters
        valid_sorts = ["downloads", "likes", "updated", "created"]
        sort_param = request.sort if request.sort in valid_sorts else "downloads"
        search_params["sort"] = sort_param

        # Only add direction for sorts that support it (downloads only supports descending)
        if sort_param != "downloads":
            # Convert direction to the format expected by HF Hub API (-1 for asc, 1 for desc)
            direction_param = -1 if request.direction == "asc" else 1
            search_params["direction"] = direction_param

        # Limit results (max 100 as per HF Hub API)
        limit = min(max(1, request.limit), 100)

        # Perform the search
        models_iterator = list_models(limit=limit, **search_params)

        # Convert models to list and extract information
        models_list = []
        for model in models_iterator:
            model_dict = {
                "id": model.id,
                "author": getattr(model, "author", None),
                "sha": getattr(model, "sha", None),
                "created_at": getattr(model, "created_at", None),
                "last_modified": getattr(model, "last_modified", None),
                "private": getattr(model, "private", False),
                "downloads": getattr(model, "downloads", 0),
                "likes": getattr(model, "likes", 0),
                "tags": getattr(model, "tags", []),
                "pipeline_tag": getattr(model, "pipeline_tag", None),
                "library_name": getattr(model, "library_name", None),
            }
            models_list.append(model_dict)

        # Prepare query info for response
        query_info = {
            "query": request.query,
            "task": request.task,
            "library": request.library,
            "author": request.author,
            "tags": request.tags,
            "limit": limit,
            "sort": sort_param,
            "direction": request.direction,  # Keep the original user-friendly format
        }

        return {
            "models": models_list,
            "total_results": len(models_list),
            "query_info": query_info,
        }

    async def on_app_initialization_complete(self, payload: AppInitializationComplete) -> None:
        """Handle app initialization complete event to download configured models.

        Args:
            payload: The app initialization complete event payload
        """
        models_to_download = payload.models_to_download
        if not models_to_download:
            logger.debug("No models configured for automatic download during app initialization")
            return

        logger.info("Starting automatic download of %d configured models", len(models_to_download))

        # Download each model in the background
        for model_id in models_to_download:
            if not model_id or not model_id.strip():
                logger.warning("Skipping empty model ID in models_to_download configuration")
                continue

            try:
                # Create download request with default parameters
                request = DownloadModelRequest(
                    model_id=model_id.strip(),
                    local_dir=None,  # Use Hugging Face cache directory
                    repo_type="model",
                    revision="main",
                    allow_patterns=None,
                    ignore_patterns=None,
                )

                logger.info("Starting automatic download for model: %s", model_id)

                # Start download in background - don't await to avoid blocking app initialization
                task = asyncio.create_task(self._handle_background_download(request))
                # Store reference but don't await to avoid blocking app initialization
                _ = task

            except Exception as e:
                logger.error("Failed to start automatic download for model '%s': %s", model_id, e)

    async def _handle_background_download(self, request: DownloadModelRequest) -> None:
        """Download a model in the background.

        Args:
            request: The download request
        """
        try:
            result = await self.on_handle_download_model_request(request)

            if isinstance(result, DownloadModelResultSuccess):
                logger.info("Automatic download completed successfully for model: %s", request.model_id)
            else:
                logger.error("Automatic download failed for model '%s': %s", request.model_id, result.result_details)

        except Exception as e:
            logger.error("Unexpected error during automatic download for model '%s': %s", request.model_id, e)
