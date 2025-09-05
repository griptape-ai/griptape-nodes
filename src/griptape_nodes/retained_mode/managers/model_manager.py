import asyncio
import contextlib
import hashlib
import json
import logging
import re
import shutil
import threading
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
from tqdm.auto import tqdm
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

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class DownloadCancelledException(Exception):
    """Exception raised when a download is cancelled by the user."""
    pass

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


def _calculate_aggregated_progress(active_instances: list[Any]) -> tuple[int, int]:
    """Calculate total downloaded and total size across all tqdm instances."""
    total_downloaded = 0
    total_size = 0

    for instance in active_instances:
        if hasattr(instance, "n") and hasattr(instance, "total"):
            instance_downloaded = getattr(instance, "n", 0) or 0
            instance_total = getattr(instance, "total", 0) or 0
            if instance_total > 0:  # Only count meaningful progress bars
                total_downloaded += instance_downloaded
                total_size += instance_total

    return total_downloaded, total_size


def _calculate_average_eta(active_instances: list[Any]) -> float | None:
    """Calculate average ETA across all active tqdm instances."""
    total_eta = 0
    eta_count = 0

    for instance in active_instances:
        try:
            if hasattr(instance, "format_dict") and instance.format_dict and instance.format_dict.get("rate"):
                rate = instance.format_dict["rate"]
                if rate > 0:
                    instance_downloaded = getattr(instance, "n", 0) or 0
                    instance_total = getattr(instance, "total", 0) or 0
                    remaining = instance_total - instance_downloaded
                    if remaining > 0:
                        eta = remaining / rate
                        total_eta += eta
                        eta_count += 1
        except (AttributeError, KeyError, ZeroDivisionError):
            continue

    return round(total_eta / eta_count, 1) if eta_count > 0 else None


def patch_tqdm_for_progress_tracking(progress_tracker: SimpleProgressTracker) -> tuple[Any, Any]:  # noqa: C901
    """Monkey patch tqdm to track progress for Hugging Face downloads."""
    # Store original methods
    original_update = tqdm.update
    original_init = tqdm.__init__

    # Track all active tqdm instances for this download
    active_tqdm_instances: list[Any] = []

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_init(self, *args, **kwargs)

        # Only track instances that have a meaningful total (file downloads)
        if hasattr(self, "total") and self.total and self.total > 0:
            self._progress_tracker = progress_tracker
            active_tqdm_instances.append(self)

        return result

    def patched_update(self: Any, n: float | None = 1) -> Any:
        result = original_update(self, n)

        # Update progress tracker by aggregating all active instances
        if hasattr(self, "_progress_tracker") and self._progress_tracker:
            # Check if download has been cancelled
            if self._progress_tracker.is_cancelled():
                # Raise an exception to stop the download
                raise DownloadCancelledException("Download cancelled by user")
            
            total_downloaded, total_size = _calculate_aggregated_progress(active_tqdm_instances)

            progress_info = {
                "downloaded_bytes": total_downloaded,
                "total_bytes": total_size,
            }

            if total_size > 0:
                progress_info["progress_percent"] = float(round((total_downloaded / total_size) * 100, 2))  # type: ignore[assignment]

                eta = _calculate_average_eta(active_tqdm_instances)
                if eta is not None:
                    progress_info["eta_seconds"] = float(eta)  # type: ignore[assignment]

            self._progress_tracker._write_status("downloading", progress_info)

        return result

    def patched_close(self: Any) -> Any:
        """Handle tqdm instance closing."""
        if self in active_tqdm_instances:
            active_tqdm_instances.remove(self)

        if hasattr(tqdm, "_original_close"):
            return tqdm._original_close(self)  # type: ignore[attr-defined]
        return None

    # Store original close method if it exists
    if hasattr(tqdm, "close"):
        tqdm._original_close = tqdm.close  # type: ignore[attr-defined]

    # Apply patches
    tqdm.update = patched_update
    tqdm.__init__ = patched_init
    tqdm.close = patched_close

    return original_update, original_init


def restore_tqdm(original_update: Any, original_init: Any) -> None:
    """Restore original tqdm methods."""
    tqdm.update = original_update
    tqdm.__init__ = original_init

    # Restore original close method if we stored it
    if hasattr(tqdm, "_original_close"):
        tqdm.close = tqdm._original_close  # type: ignore[attr-defined]
        delattr(tqdm, "_original_close")


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
        if event_manager is not None:
            # Register our request handlers
            event_manager.assign_manager_to_request_type(DownloadModelRequest, self.on_handle_download_model_request)
            event_manager.assign_manager_to_request_type(ListModelsRequest, self.on_handle_list_models_request)
            event_manager.assign_manager_to_request_type(DeleteModelRequest, self.on_handle_delete_model_request)
            event_manager.assign_manager_to_request_type(
                GetModelDownloadStatusRequest, self.on_handle_get_download_status_request
            )
            event_manager.assign_manager_to_request_type(SearchModelsRequest, self.on_handle_search_models_request)
            event_manager.assign_manager_to_request_type(CancelModelDownloadRequest, self.on_handle_cancel_download_request)

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
            else:
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
        """Model download implementation with progress tracking.

        Args:
            download_params: Dictionary containing download parameters
            model_id: The model identifier for progress tracking

        Returns:
            Path: Local path where the model was downloaded

        Raises:
            RuntimeError: If download was cancelled
        """
        # Create progress tracking file
        progress_tracker = SimpleProgressTracker(model_id)

        # Validate parameters and build download kwargs
        download_kwargs = self._build_download_kwargs(download_params)

        # Monkey patch tqdm for progress tracking
        original_update, original_init = patch_tqdm_for_progress_tracking(progress_tracker)

        try:
            # Execute download with progress tracking and cancellation monitoring
            local_path = self._download_with_cancellation_check(download_kwargs, progress_tracker)
                
            progress_tracker.mark_completed()
            return Path(local_path)
        except DownloadCancelledException as e:
            # Download was cancelled via status file
            progress_tracker.mark_cancelled()
            raise RuntimeError("Download cancelled by user") from e
        except RuntimeError as e:
            if "cancelled" in str(e).lower():
                progress_tracker.mark_cancelled()
            else:
                progress_tracker.mark_failed(str(e))
            raise
        except Exception as e:
            progress_tracker.mark_failed(str(e))
            raise
        finally:
            # Always restore original tqdm methods
            restore_tqdm(original_update, original_init)

    def _download_with_cancellation_check(self, download_kwargs: dict, progress_tracker: SimpleProgressTracker) -> str:
        """Execute download with periodic cancellation checks.
        
        Args:
            download_kwargs: Parameters for snapshot_download
            progress_tracker: Progress tracker to check for cancellation
            
        Returns:
            str: Local path where the model was downloaded
            
        Raises:
            DownloadCancelledException: If download was cancelled
        """
        download_result = None
        download_exception = None
        cancel_event = threading.Event()
        
        def download_worker():
            nonlocal download_result, download_exception
            try:
                # Add the cancel event to the download process
                download_result = self._interruptible_snapshot_download(download_kwargs, cancel_event, progress_tracker)
            except Exception as e:
                download_exception = e
        
        # Start download in a separate thread
        download_thread = threading.Thread(target=download_worker)
        download_thread.daemon = True
        download_thread.start()
        
        # Monitor for cancellation while download is running
        while download_thread.is_alive():
            if progress_tracker.is_cancelled():
                # Signal the download thread to cancel
                cancel_event.set()
                # Give it a moment to respond, then raise exception
                download_thread.join(timeout=2.0)
                raise DownloadCancelledException("Download cancelled by user")
            
            # Check every second
            download_thread.join(timeout=1.0)
        
        # Download thread finished, check results
        if download_exception:
            raise download_exception
        
        if download_result is None:
            raise RuntimeError("Download completed but no result was returned")
            
        return download_result

    def _interruptible_snapshot_download(self, download_kwargs: dict, cancel_event: threading.Event, progress_tracker: SimpleProgressTracker) -> str:
        """Run snapshot_download with periodic cancellation checks.
        
        Args:
            download_kwargs: Parameters for snapshot_download
            cancel_event: Event to signal cancellation
            progress_tracker: Progress tracker for status updates
            
        Returns:
            str: Local path where model was downloaded
            
        Raises:
            DownloadCancelledException: If cancellation was requested
        """
        # Monkey patch the requests library to check for cancellation during HTTP operations
        import requests
        
        original_get = requests.get
        original_request = requests.Session.request
        
        def cancellation_aware_get(*args, **kwargs):
            if cancel_event.is_set():
                raise DownloadCancelledException("Download cancelled during HTTP request")
            
            # Add a timeout to prevent hanging
            if 'timeout' not in kwargs:
                kwargs['timeout'] = 30
                
            return original_get(*args, **kwargs)
        
        def cancellation_aware_request(self, method, url, **kwargs):
            if cancel_event.is_set():
                raise DownloadCancelledException("Download cancelled during HTTP request")
                
            # Add a timeout to prevent hanging  
            if 'timeout' not in kwargs:
                kwargs['timeout'] = 30
                
            return original_request(self, method, url, **kwargs)
        
        # Apply patches
        requests.get = cancellation_aware_get
        requests.Session.request = cancellation_aware_request
        
        try:
            # Also check for cancellation before starting
            if cancel_event.is_set():
                raise DownloadCancelledException("Download cancelled before starting")
                
            result = snapshot_download(**download_kwargs)  # type: ignore[arg-type]
            
            # Final check after download
            if cancel_event.is_set():
                raise DownloadCancelledException("Download cancelled after completion")
                
            return result
        finally:
            # Always restore original functions
            requests.get = original_get
            requests.Session.request = original_request

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

        This method cancels an active model download by signaling the download thread
        to stop and updating the download status appropriately.

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
            # Check the status file to see if download is active
            status = get_download_status(parsed_model_id)
            
            if status:
                status_str = status.get("status", "unknown")
                
                if status_str == "downloading":
                    # Download is active, mark it as cancelled in the status file
                    model_id_hash = hashlib.sha256(parsed_model_id.encode()).hexdigest()[:16]
                    status_file = MODEL_DOWNLOADS_DIR / f"{model_id_hash}.json"
                    
                    # Update status to cancelled
                    try:
                        status["status"] = "cancelled"
                        status["updated_at"] = datetime.now(tz=UTC).isoformat()
                        with status_file.open("w", encoding="utf-8") as f:
                            json.dump(status, f, indent=2)
                            
                        result_details = f"Cancellation requested for active download of '{parsed_model_id}'"
                        logger.info(result_details)

                        return CancelModelDownloadResultSuccess(
                            model_id=parsed_model_id,
                            was_cancelled=True,
                            result_details=result_details,
                        )
                    except Exception as file_error:
                        raise RuntimeError(f"Failed to update status file: {file_error}") from file_error
                        
                elif status_str in ["completed", "failed", "cancelled"]:
                    return CancelModelDownloadResultSuccess(
                        model_id=parsed_model_id,
                        was_cancelled=False,
                        result_details=f"Download for '{parsed_model_id}' was already {status_str}",
                    )
                else:
                    return CancelModelDownloadResultFailure(
                        result_details=f"Download for '{parsed_model_id}' is in unknown state: {status_str}",
                    )
            else:
                # No download status file found
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
