from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class DownloadModelRequest(RequestPayload):
    """Download a model from Hugging Face Hub.

    Use when: Downloading models for local inference, caching models for offline use,
    retrieving specific model versions or files from Hugging Face repositories.

    Args:
        model_id: Model identifier (e.g., "microsoft/DialoGPT-medium") or full URL to Hugging Face model
        local_dir: Optional local directory to download the model to (defaults to Hugging Face cache)
        repo_type: Type of repository ("model", "dataset", or "space"). Defaults to "model"
        revision: Git revision (branch, tag, or commit hash) to download. Defaults to "main"
        allow_patterns: List of glob patterns to include when downloading. None means all files
        ignore_patterns: List of glob patterns to exclude when downloading

    Results: DownloadModelResultSuccess (with local_path) | DownloadModelResultFailure (download error)
    """

    model_id: str
    local_dir: str | None = None
    repo_type: str = "model"
    revision: str = "main"
    allow_patterns: list[str] | None = None
    ignore_patterns: list[str] | None = None


@dataclass
@PayloadRegistry.register
class DownloadModelResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Model download completed successfully.

    Args:
        local_path: Local file system path where the model was downloaded
        model_id: The model ID that was downloaded
        repo_info: Additional repository information returned from the download
    """

    local_path: str
    model_id: str
    repo_info: dict[str, Any] | None = None


@dataclass
@PayloadRegistry.register
class DownloadModelResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Model download failed. Common causes: invalid model ID, network error, authentication required, storage full."""


@dataclass
@PayloadRegistry.register
class ListModelsRequest(RequestPayload):
    """List all downloaded models from the local cache.

    Use when: Viewing what models are available locally, checking cache usage,
    managing local model storage.

    Results: ListModelsResultSuccess (with model list) | ListModelsResultFailure (listing error)
    """


@dataclass
@PayloadRegistry.register
class ListModelsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Model listing completed successfully.

    Args:
        models: List of model information dictionaries containing model_id, local_path, size_bytes, etc.
    """

    models: list[dict[str, Any]]


@dataclass
@PayloadRegistry.register
class ListModelsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Model listing failed. Common causes: cache directory access error, filesystem error."""


@dataclass
@PayloadRegistry.register
class DeleteModelRequest(RequestPayload):
    """Delete a downloaded model from the local cache.

    Use when: Cleaning up disk space, removing unused models, managing local storage.

    Args:
        model_id: Model identifier to delete from local cache

    Results: DeleteModelResultSuccess (deletion confirmed) | DeleteModelResultFailure (deletion error)
    """

    model_id: str


@dataclass
@PayloadRegistry.register
class DeleteModelResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Model deletion completed successfully.

    Args:
        model_id: The model ID that was deleted
        deleted_path: Local path that was removed
    """

    model_id: str
    deleted_path: str


@dataclass
@PayloadRegistry.register
class DeleteModelResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Model deletion failed. Common causes: model not found, filesystem error, permission denied."""


@dataclass
@PayloadRegistry.register
class GetModelDownloadStatusRequest(RequestPayload):
    """Get download status for a specific model or list all downloads.

    Use when: Checking progress of ongoing downloads, viewing download history,
    monitoring download completion.

    Args:
        model_id: Optional model identifier to get status for. If None, returns all downloads.

    Results: GetModelDownloadStatusResultSuccess (with status data) | GetModelDownloadStatusResultFailure (query error)
    """

    model_id: str | None = None


@dataclass
@PayloadRegistry.register
class GetModelDownloadStatusResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Model download status retrieved successfully.

    Args:
        downloads: List of download status dictionaries or single status if model_id was specified
    """

    downloads: list[dict[str, Any]]


@dataclass
@PayloadRegistry.register
class GetModelDownloadStatusResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Model download status query failed. Common causes: filesystem error, invalid model ID."""


@dataclass
@PayloadRegistry.register
class SearchModelsRequest(RequestPayload):
    """Search for models on Hugging Face Hub.

    Use when: Finding models by name, filtering models by task or library,
    discovering available models for specific use cases.

    Args:
        query: Search query string to match against model names and descriptions
        task: Filter by task type (e.g., "text-generation", "image-classification")
        library: Filter by library (e.g., "transformers", "diffusers", "timm")
        author: Filter by author/organization name
        tags: List of tags to filter by
        limit: Maximum number of results to return (default: 20, max: 100)
        sort: Sort results by "downloads", "likes", "updated", or "created" (default: "downloads")
        direction: Sort direction "asc" or "desc" (default: "desc")

    Results: SearchModelsResultSuccess (with model list) | SearchModelsResultFailure (search error)
    """

    query: str | None = None
    task: str | None = None
    library: str | None = None
    author: str | None = None
    tags: list[str] | None = None
    limit: int = 20
    sort: str = "downloads"
    direction: str = "desc"


@dataclass
@PayloadRegistry.register
class SearchModelsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Model search completed successfully.

    Args:
        models: List of model information dictionaries containing id, author, downloads, etc.
        total_results: Total number of models matching the search criteria
        query_info: Information about the search query parameters used
    """

    models: list[dict[str, Any]]
    total_results: int
    query_info: dict[str, Any]


@dataclass
@PayloadRegistry.register
class SearchModelsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Model search failed. Common causes: network error, invalid parameters, API limits."""


@dataclass
@PayloadRegistry.register
class CancelModelDownloadRequest(RequestPayload):
    """Cancel an active model download.

    Use when: Stopping a long-running download, freeing up bandwidth,
    aborting downloads that are no longer needed.

    Args:
        model_id: Model identifier to cancel download for

    Results: CancelModelDownloadResultSuccess (cancellation status) | CancelModelDownloadResultFailure (cancellation error)
    """

    model_id: str


@dataclass
@PayloadRegistry.register
class CancelModelDownloadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Model download cancellation completed successfully.

    Args:
        model_id: The model ID that was targeted for cancellation
        was_cancelled: True if download was active and cancelled, False if already completed/failed
    """

    model_id: str
    was_cancelled: bool


@dataclass
@PayloadRegistry.register
class CancelModelDownloadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Model download cancellation failed. Common causes: no active download found, filesystem error."""
