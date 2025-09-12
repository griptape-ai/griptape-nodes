from dataclasses import dataclass
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.video_utils import (
    download_video_to_temp_file,
    extract_url_from_video_object,
    is_downloadable_video_url,
    is_video_url_artifact,
)

DEFAULT_FILENAME = "griptape_nodes.mp4"


@dataclass
class VideoInput:
    """Normalized video input - single source of truth."""

    data: bytes | None = None  # Video bytes (if we have them)
    source_url: str | None = None  # URL to download (if we need to)
    format_hint: str | None = None  # Format from source

    @property
    def needs_download(self) -> bool:
        """True if we need to download from URL."""
        return self.source_url is not None and self.data is None


class DownloadedVideoArtifact:
    """Simple artifact for downloaded video bytes."""

    def __init__(self, value: bytes, detected_format: str | None = None):
        self.value = value
        self.detected_format = detected_format


class SaveVideo(SuccessFailureNode):
    """Save a video to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add video input parameter
        self.add_parameter(
            Parameter(
                name="video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The video to save to file",
            )
        )

        # Add output path parameter
        self.add_parameter(
            Parameter(
                name="output_path",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=DEFAULT_FILENAME,
                tooltip="The output filename. The file extension will be auto-determined from video format.",
            )
        )

        # Save options parameters in a collapsible ParameterGroup
        with ParameterGroup(name="Save Options") as save_options_group:
            save_options_group.ui_options = {"collapsed": True}

            self.allow_creating_folders = Parameter(
                name="allow_creating_folders",
                tooltip="Allow creating parent directories if they don't exist",
                type="bool",
                default_value=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

            self.overwrite_existing = Parameter(
                name="overwrite_existing",
                tooltip="Allow overwriting existing files",
                type="bool",
                default_value=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

        self.add_node_element(save_options_group)

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the video save operation result",
            result_details_placeholder="Details on the save attempt will be presented here.",
        )

    def _get_video_extension(self, video_value: Any) -> str | None:
        """Extract and return the file extension from video data."""
        if video_value is None:
            return None

        # Try to extract extension from any VideoUrlArtifact URL
        if is_video_url_artifact(video_value) and isinstance(video_value.value, str):
            url = video_value.value
            filename_from_url = url.split("/")[-1].split("?")[0]
            if "." in filename_from_url:
                return Path(filename_from_url).suffix

        # Try to get extension from dict representation
        elif isinstance(video_value, dict) and "name" in video_value:
            filename = video_value["name"]
            if "." in filename:
                return Path(filename).suffix

        return None

    def after_incoming_connection(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> None:
        """Handle automatic extension detection when video connection is made."""
        if target_parameter.name == "video":
            # Get video value from the source node
            video_value = source_node.parameter_output_values.get(source_parameter.name)
            if video_value is None:
                video_value = source_node.parameter_values.get(source_parameter.name)

            extension = self._get_video_extension(video_value)
            if extension:
                current_output_path = self.get_parameter_value("output_path")
                new_filename = str(Path(current_output_path).with_suffix(extension))
                self.parameter_output_values["output_path"] = new_filename
                logger.info(f"Updated extension to {extension}: {new_filename}")

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def _extract_format_from_url(self, url: str) -> str | None:
        """Extract format hint from URL."""
        if "." in url:
            extension = url.split(".")[-1].split("?")[0]  # Remove query params
            if extension.lower() in ["mp4", "avi", "mov", "mkv", "flv", "wmv", "webm", "m4v"]:
                return extension.lower()
        return None

    def _extract_bytes_from_artifact(self, artifact: Any) -> bytes | None:
        """Extract bytes from various artifact types."""
        if isinstance(artifact, dict) and "value" in artifact:
            value = artifact["value"]
            if isinstance(value, bytes):
                return value
            if isinstance(value, str) and "base64," in value:
                import base64

                return base64.b64decode(value.split("base64,")[1])

        if hasattr(artifact, "value") and isinstance(artifact.value, bytes):  # type: ignore[attr-defined]
            return artifact.value  # type: ignore[attr-defined]

        return None

    def _extract_format_from_artifact(self, artifact: Any) -> str | None:
        """Extract format hint from various artifact types."""
        # Check dict-style artifacts
        if isinstance(artifact, dict):
            if "type" in artifact and isinstance(artifact["type"], str) and "/" in artifact["type"]:
                return artifact["type"].split("/")[1]
            if "format" in artifact and isinstance(artifact["format"], str):
                return artifact["format"]

        # Check artifact metadata
        if hasattr(artifact, "meta"):
            meta = artifact.meta  # type: ignore[attr-defined]
            if meta and isinstance(meta, dict):
                if "format" in meta and isinstance(meta["format"], str):
                    return meta["format"]
                if "content_type" in meta and isinstance(meta["content_type"], str) and "/" in meta["content_type"]:
                    return meta["content_type"].split("/")[1]

        # Check for detected_format (our DownloadedVideoArtifact)
        if hasattr(artifact, "detected_format"):
            detected_format = artifact.detected_format  # type: ignore[attr-defined]
            if isinstance(detected_format, str):
                return detected_format

        return None

    def _normalize_input(self, raw_input: Any) -> VideoInput:
        """Convert ANY input to VideoInput. Single source of truth for input handling."""
        if not raw_input:
            return VideoInput()

        # Check if input contains a downloadable URL (handles all URL cases)
        if is_downloadable_video_url(raw_input):
            url = extract_url_from_video_object(raw_input)
            if url:
                return VideoInput(source_url=url, format_hint=self._extract_format_from_url(url))

        # Handle all other cases - try to extract bytes and format
        video_bytes = self._extract_bytes_from_artifact(raw_input)
        format_hint = self._extract_format_from_artifact(raw_input)

        return VideoInput(data=video_bytes, format_hint=format_hint)

    async def _download_video(self, video_input: VideoInput) -> VideoInput:
        """Download video from URL, return VideoInput with data populated."""
        if not video_input.source_url:
            msg = "No source URL provided for download"
            raise ValueError(msg)

        # Update status to show download starting
        self._set_status_results(
            was_successful=True, result_details=f"Downloading video from URL: {video_input.source_url}"
        )

        # Download to temp file
        download_result = await download_video_to_temp_file(video_input.source_url)

        try:
            # Update status to show download completed
            file_size = download_result.temp_file_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            self._set_status_results(
                was_successful=True,
                result_details=f"Downloaded video ({size_mb:.1f}MB) to temporary file, processing...",
            )

            # Read video bytes from temp file
            video_bytes = download_result.temp_file_path.read_bytes()

            return VideoInput(
                data=video_bytes,
                source_url=video_input.source_url,
                format_hint=download_result.detected_format or video_input.format_hint,
            )

        finally:
            # Always cleanup temp file
            if download_result.temp_file_path.exists():
                download_result.temp_file_path.unlink(missing_ok=True)

    def _save_video_bytes(self, video_bytes: bytes, format_hint: str | None) -> str:
        """Save bytes to appropriate location, return saved path."""
        output_file = self.get_parameter_value("output_path") or DEFAULT_FILENAME

        # Set output values BEFORE processing
        self.parameter_output_values["output_path"] = output_file

        # Auto-determine filename with correct extension if we have format hint
        if format_hint:
            output_path = Path(output_file)
            new_extension = f".{format_hint.lstrip('.')}"  # Ensure leading dot
            if output_path.suffix.lower() != new_extension.lower():
                output_file = str(output_path.with_suffix(new_extension))
                self.parameter_output_values["output_path"] = output_file

        # Get save options
        allow_creating_folders = self.get_parameter_value(self.allow_creating_folders.name)
        overwrite_existing = self.get_parameter_value(self.overwrite_existing.name)

        # Save based on path type
        output_path = Path(output_file)
        if output_path.is_absolute():
            # Absolute path: save directly to filesystem
            return self._save_to_filesystem_direct(
                video_bytes=video_bytes,
                output_path=output_path,
                allow_creating_folders=allow_creating_folders,
                overwrite_existing=overwrite_existing,
            )
        # Relative path: use static file manager
        return self._save_to_static_storage_direct(
            video_bytes=video_bytes, output_file=output_file, overwrite_existing=overwrite_existing
        )

    def _report_warning(self, _message: str) -> None:
        """Report warning status."""
        output_file = self.get_parameter_value("output_path") or DEFAULT_FILENAME
        self.parameter_output_values["output_path"] = output_file

        result_details = (
            f"No video to save (warning)\n"
            f"Input: No video input\n"
            f"Requested filename: {output_file}\n"
            f"Result: No file created"
        )

        self._set_status_results(was_successful=True, result_details=f"WARNING: {result_details}")

    def _report_success(self, saved_path: str, downloaded_from_url: str | None) -> None:
        """Report success with download info if applicable."""
        output_file = self.get_parameter_value("output_path") or DEFAULT_FILENAME

        result_details = f"Video saved successfully\nRequested filename: {output_file}\nSaved to: {saved_path}"

        # Add download info if available
        if downloaded_from_url:
            result_details = f"Downloaded from: {downloaded_from_url}\n{result_details}"

        self._set_status_results(was_successful=True, result_details=f"SUCCESS: {result_details}")
        logger.info(f"Saved video: {saved_path}")

    def _report_error(self, error_details: str, exception: Exception | None = None) -> None:
        """Report error status."""
        failure_details = f"Video save failed\nError: {error_details}"

        if exception:
            failure_details += f"\nException type: {type(exception).__name__}"
            if exception.__cause__:
                failure_details += f"\nCause: {exception.__cause__}"

        self._set_status_results(was_successful=False, result_details=f"FAILURE: {failure_details}")
        logger.error(f"Error saving video: {error_details}")

        # Use the helper to handle exception based on connection status
        self._handle_failure_exception(RuntimeError(error_details))

    def _save_to_filesystem_direct(
        self, video_bytes: bytes, output_path: Path, *, allow_creating_folders: bool, overwrite_existing: bool
    ) -> str:
        """Save video bytes directly to filesystem at the specified absolute path."""
        # Check if file exists and overwrite is disabled
        if output_path.exists() and not overwrite_existing:
            msg = f"File already exists and overwrite_existing is disabled: {output_path}"
            raise RuntimeError(msg)

        # Handle parent directory creation
        if allow_creating_folders:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        elif not output_path.parent.exists():
            msg = f"Parent directory does not exist and allow_creating_folders is disabled: {output_path.parent}"
            raise RuntimeError(msg)

        # Write video bytes directly to file
        output_path.write_bytes(video_bytes)
        return str(output_path)

    def _save_to_static_storage_direct(self, video_bytes: bytes, output_file: str, *, overwrite_existing: bool) -> str:
        """Save video bytes using the static file manager."""
        # Check if file exists in static storage and overwrite is disabled
        if not overwrite_existing:
            from griptape_nodes.retained_mode.events.static_file_events import (
                CreateStaticFileDownloadUrlRequest,
                CreateStaticFileDownloadUrlResultFailure,
            )

            static_files_manager = GriptapeNodes.StaticFilesManager()
            request = CreateStaticFileDownloadUrlRequest(file_name=output_file)
            result = static_files_manager.on_handle_create_static_file_download_url_request(request)

            if not isinstance(result, CreateStaticFileDownloadUrlResultFailure):
                msg = f"File already exists in static storage and overwrite_existing is disabled: {output_file}"
                raise RuntimeError(msg)

        # Save to static storage
        return GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, output_file)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = []

        # Validate that we have a video.
        video = self.parameter_values.get("video")
        if not video:
            exceptions.append(ValueError("Video parameter is required"))

        return exceptions if exceptions else None

    async def aprocess(self) -> None:
        """Async process method - linear pipeline approach."""
        # Reset execution state at the very top
        self._clear_execution_status()

        try:
            # Step 1: Normalize input (handles ALL artifact types)
            video_input = self._normalize_input(self.get_parameter_value("video"))

            # Step 2: Download if needed (simple conditional)
            if video_input.needs_download:
                video_input = await self._download_video(video_input)

            # Step 3: Validate we have data
            if not video_input.data:
                self._report_warning("No video data available")
                return

            # Step 4: Save video bytes
            saved_path = self._save_video_bytes(video_input.data, video_input.format_hint)

            # Step 5: Report success
            self._report_success(saved_path, video_input.source_url)

        except Exception as e:
            self._report_error(str(e), e)

    def process(self) -> None:
        """Sync process method - handles non-URL videos only."""
        # Reset execution state and result details at the start of each run
        self._clear_execution_status()

        try:
            # Step 1: Normalize input
            video_input = self._normalize_input(self.get_parameter_value("video"))

            # Step 2: Check if we need async download (not supported in sync)
            if video_input.needs_download:
                self._report_error(
                    "URL video downloads require async processing. This should not happen in normal operation."
                )
                return

            # Step 3: Validate we have data
            if not video_input.data:
                self._report_warning("No video data available")
                return

            # Step 4: Save video bytes
            saved_path = self._save_video_bytes(video_input.data, video_input.format_hint)

            # Step 5: Report success
            self._report_success(saved_path, None)

        except Exception as e:
            self._report_error(str(e), e)
