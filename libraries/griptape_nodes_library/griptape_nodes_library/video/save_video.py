from enum import StrEnum, auto
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
    VideoDownloadResult,
    detect_video_format,
    download_video_to_temp_file,
    to_video_artifact,
)
from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact

DEFAULT_FILENAME = "griptape_nodes.mp4"
PREVIEW_LENGTH = 50


class DownloadedVideoArtifact:
    """Simple artifact for downloaded video bytes."""

    def __init__(self, value: bytes, detected_format: str | None = None):
        self.value = value
        self.detected_format = detected_format


class SaveVideoStatus(StrEnum):
    """Status enum for save video operations."""

    SUCCESS = auto()
    WARNING = auto()
    FAILURE = auto()


def auto_determine_filename(base_filename: str, detected_format: str | None) -> str:
    """Auto-determine the output filename with the correct extension.

    Args:
        base_filename: The user-provided filename
        detected_format: The detected video format

    Returns:
        The filename with the appropriate extension
    """
    if detected_format is None:
        return base_filename

    base_path = Path(base_filename)

    # If the user already provided an extension, keep it unless it's generic
    current_ext = base_path.suffix.lower()
    if current_ext and current_ext != ".mp4":  # Don't override if user specified non-default
        return base_filename

    # Preserve the parent directory and use detected format
    return str(base_path.with_suffix(f".{detected_format}"))


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

        # Try to extract extension from VideoUrlArtifact URL
        if hasattr(video_value, "value") and isinstance(video_value.value, str):
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

    def _is_video_url_needing_download(self, video: Any) -> bool:
        """Check if video input is a URL string that needs downloading."""
        if isinstance(video, str):
            # Direct URL string
            return video.startswith(("http://", "https://"))

        # Check for any VideoUrlArtifact-like object (regardless of which library it's from)
        if hasattr(video, "value") and hasattr(video, "__class__") and "VideoUrlArtifact" in video.__class__.__name__:
            # Any VideoUrlArtifact with URL that might need downloading
            return video.value.startswith(("http://", "https://"))

        return False

    def _extract_url_from_video(self, video: Any) -> str:
        """Extract URL from video input."""
        if isinstance(video, str):
            return video

        # Check for any VideoUrlArtifact-like object (regardless of which library it's from)
        if hasattr(video, "value") and hasattr(video, "__class__") and "VideoUrlArtifact" in video.__class__.__name__:
            return video.value

        error_details = f"Cannot extract URL from video type: {type(video).__name__}"
        raise ValueError(error_details)

    def _create_video_artifact_from_temp_file(self, download_result: VideoDownloadResult) -> DownloadedVideoArtifact:
        """Create video artifact from downloaded temp file."""
        # Read video bytes from temp file
        video_bytes = download_result.temp_file_path.read_bytes()

        # Use detected format or default to mp4
        format_ext = download_result.detected_format or "mp4"

        # Create artifact that bypasses the dict_to_video_url_artifact conversion
        return DownloadedVideoArtifact(video_bytes, format_ext)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = []

        # Validate that we have a video.
        video = self.parameter_values.get("video")
        if not video:
            exceptions.append(ValueError("Video parameter is required"))

        return exceptions if exceptions else None

    def _process_video_save(self, video: Any, downloaded_from_url: str | None = None) -> None:
        """Process video saving with the provided video input."""
        output_file = self.get_parameter_value("output_path") or DEFAULT_FILENAME

        # Set output values BEFORE processing
        self.parameter_output_values["output_path"] = output_file

        if not video:
            # Blank video is a warning, not a failure
            warning_details = "No video provided to save"
            logger.warning(warning_details)
            self._handle_execution_result(
                status=SaveVideoStatus.WARNING,
                saved_path="",
                input_info="No video input",
                output_file=output_file,
                details=warning_details,
                downloaded_from_url=downloaded_from_url,
            )
            return

        # Process the video
        self._process_video(video, output_file, downloaded_from_url=downloaded_from_url)

    async def aprocess(self) -> None:
        """Async process method to handle URL downloading."""
        # Reset execution state at the very top
        self._clear_execution_status()

        video = self.get_parameter_value("video")

        # Check if we need to download from URL
        if self._is_video_url_needing_download(video):
            await self._handle_url_download_and_process(video)
        else:
            # No URL download needed - process original video
            self._process_video_save(video)

    def process(self) -> None:
        """Sync process method - handles non-URL videos only."""
        # Reset execution state and result details at the start of each run
        self._clear_execution_status()

        video = self.get_parameter_value("video")

        # For sync processing, we can only handle non-URL videos
        if self._is_video_url_needing_download(video):
            error_details = "URL video downloads require async processing. This should not happen in normal operation."
            self._handle_execution_result(
                status=SaveVideoStatus.FAILURE,
                saved_path="",
                input_info=f"URL: {self._extract_url_from_video(video)}",
                output_file=self.get_parameter_value("output_path") or DEFAULT_FILENAME,
                details=error_details,
            )
            self._handle_failure_exception(RuntimeError(error_details))
            return

        # Process non-URL video normally
        self._process_video_save(video)

    async def _handle_url_download_and_process(self, video: Any) -> None:
        """Handle URL download and processing with tight error handling."""
        url = self._extract_url_from_video(video)
        temp_file_to_cleanup = None

        try:
            # Update status to show download starting
            self._set_status_results(was_successful=True, result_details=f"Downloading video from URL: {url}")

            # Download to temp file
            download_result = await download_video_to_temp_file(url)
            temp_file_to_cleanup = download_result.temp_file_path

            # Update status to show download completed
            file_size = download_result.temp_file_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            self._set_status_results(
                was_successful=True,
                result_details=f"Downloaded video ({size_mb:.1f}MB) to temporary file, processing...",
            )

            # Create video artifact from temp file
            downloaded_video = self._create_video_artifact_from_temp_file(download_result)

            # Call process method with downloaded video
            self._process_video_save(downloaded_video, downloaded_from_url=url)

        except Exception as e:
            # Handle URL download errors with existing error pipeline
            error_details = f"Failed to download video from URL: {e}"
            self._handle_execution_result(
                status=SaveVideoStatus.FAILURE,
                saved_path="",
                input_info=f"URL: {url}",
                output_file=self.get_parameter_value("output_path") or DEFAULT_FILENAME,
                details=error_details,
                exception=e,
            )
            # Use the helper to handle exception based on connection status
            self._handle_failure_exception(RuntimeError(error_details))
        finally:
            # Always cleanup temp file
            if temp_file_to_cleanup and temp_file_to_cleanup.exists():
                temp_file_to_cleanup.unlink(missing_ok=True)

    def _process_video(self, video: Any, output_file: str, downloaded_from_url: str | None = None) -> None:
        """Process the video through all steps."""
        # Capture input source details for forensics
        input_info = self._get_input_info(video)

        # Step 1: Detect video format
        detected_format = self._detect_video_format(video, input_info, output_file)
        if detected_format is None:
            return

        # Step 2: Auto-determine filename with correct extension
        output_file = self._auto_determine_filename(output_file, detected_format)

        # Step 3: Convert to video artifact
        video_artifact = self._convert_to_artifact(video, input_info, output_file)
        if video_artifact is None:
            return

        # Step 4: Extract video bytes
        video_bytes = self._extract_video_bytes(video_artifact, input_info, output_file)
        if video_bytes is None:
            return

        # Step 5: Save video using appropriate method
        saved_path, path_method = self._save_video(video_bytes, output_file, input_info)
        if saved_path is None:
            return

        # Success case with path method info
        success_details = f"Video saved successfully via {path_method} with format: {detected_format or 'unknown'}"
        self._handle_execution_result(
            status=SaveVideoStatus.SUCCESS,
            saved_path=saved_path,
            input_info=input_info,
            output_file=output_file,
            details=success_details,
            downloaded_from_url=downloaded_from_url,
        )
        logger.info(f"Saved video: {saved_path}")

    def _detect_video_format(self, video: Any, input_info: str, output_file: str) -> str | None:
        """Detect video format. Returns None on failure."""
        try:
            detected_format = detect_video_format(video)
            logger.debug(f"Auto-detected video format: {detected_format or 'unknown'}")
        except Exception as e:
            error_details = (
                f"Unable to detect video format. Check that the video input is valid and supported. Error: {e!s}"
            )
            self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
            return None
        else:
            return detected_format

    def _auto_determine_filename(self, output_file: str, detected_format: str | None) -> str:
        """Auto-determine filename with correct extension. Returns updated filename."""
        try:
            if detected_format:
                output_file = auto_determine_filename(output_file, detected_format)
                # Update output path after auto-determination
                self.parameter_output_values["output_path"] = output_file
                logger.debug(f"Using filename: {output_file}")
        except Exception as e:
            # Filename determination failure is a warning, not an error - continue with original filename
            warning_details = f"Could not auto-determine filename with format '{detected_format}'. Using original filename '{output_file}'. Warning: {e!s}"
            logger.warning(warning_details)
            # Continue processing with the original filename
        return output_file

    def _convert_to_artifact(self, video: Any, input_info: str, output_file: str) -> Any:
        """Convert to video artifact. Returns None on failure."""
        try:
            return to_video_artifact(video)
        except Exception as e:
            error_details = (
                f"Unable to process video input. Ensure the video data is in a supported format. Error: {e!s}"
            )
            self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
            return None

    def _extract_video_bytes(self, video_artifact: Any, input_info: str, output_file: str) -> bytes | None:
        """Extract video bytes from artifact. Returns None on failure."""
        try:
            if isinstance(video_artifact, VideoUrlArtifact):
                # For VideoUrlArtifact, we need to get the bytes from the URL
                video_bytes = video_artifact.to_bytes()
            else:
                # Assume it has a value attribute with bytes
                video_bytes = video_artifact.value

            # Validate that we have actual bytes
            self._validate_video_bytes(video_bytes)
        except Exception as e:
            if "contains no data" in str(e):
                error_details = "Video artifact is empty. Check that your video input contains actual video data."
            else:
                error_details = f"Failed to extract video data from the artifact. This may indicate a corrupted or unsupported video format. Error: {e!s}"
            self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
            return None
        else:
            return video_bytes

    def _save_video(self, video_bytes: bytes, output_file: str, input_info: str) -> tuple[str | None, str]:
        """Save video using appropriate method. Returns (saved_path, path_method) or (None, method)."""
        # Get save options
        allow_creating_folders = self.get_parameter_value(self.allow_creating_folders.name)
        overwrite_existing = self.get_parameter_value(self.overwrite_existing.name)

        try:
            output_path = Path(output_file)
            if output_path.is_absolute():
                # Full path: save directly to filesystem
                saved_path = self._save_to_filesystem(
                    video_bytes=video_bytes,
                    output_path=output_path,
                    allow_creating_folders=allow_creating_folders,
                    overwrite_existing=overwrite_existing,
                )
                path_method = "filesystem"
            else:
                # Relative path: use static file manager
                saved_path = self._save_to_static_storage(
                    video_bytes=video_bytes, output_file=output_file, overwrite_existing=overwrite_existing
                )
                path_method = "static storage"
        except Exception as e:
            error_details = f"Failed to save video file '{output_file}': {e!s}"
            self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
            return None, "unknown"
        else:
            return saved_path, path_method

    def _get_input_info(self, video: Any) -> str:
        """Get input information for forensics logging."""
        input_type = type(video).__name__
        if isinstance(video, dict):
            return f"Dictionary input with type: {video.get('type', 'unknown')}"
        if isinstance(video, VideoUrlArtifact):
            return f"VideoUrlArtifact with URL: {video.value}"
        return f"VideoArtifact of type: {input_type}"

    def _get_input_info_for_failure(self, video: Any) -> str:
        """Get detailed input information for failure forensics logging."""
        input_type = type(video).__name__
        if isinstance(video, dict):
            input_info = f"Dictionary input with type: {video.get('type', 'unknown')}"
            if "value" in video:
                value_str = str(video["value"])
                value_preview = value_str[:PREVIEW_LENGTH] + "..." if len(value_str) > PREVIEW_LENGTH else value_str
                input_info += f", value preview: {value_preview}"
            return input_info
        if isinstance(video, VideoUrlArtifact):
            return f"VideoUrlArtifact with URL: {video.value}"
        return f"VideoArtifact of type: {input_type}"

    def _handle_execution_result(  # noqa: PLR0913
        self,
        status: SaveVideoStatus,
        saved_path: str,
        input_info: str,
        output_file: str,
        details: str,
        exception: Exception | None = None,
        downloaded_from_url: str | None = None,
    ) -> None:
        """Handle execution result for all cases."""
        match status:
            case SaveVideoStatus.FAILURE:
                # Get detailed input info for failures (including dictionary preview)
                detailed_input_info = self._get_input_info_for_failure(self.get_parameter_value("video"))

                failure_details = f"Video save failed\nInput: {detailed_input_info}\nError: {details}"

                if exception:
                    failure_details += f"\nException type: {type(exception).__name__}"
                    if exception.__cause__:
                        failure_details += f"\nCause: {exception.__cause__}"

                self._set_status_results(was_successful=False, result_details=f"{status}: {failure_details}")
                logger.error(f"Error saving video: {details}")

            case SaveVideoStatus.WARNING:
                result_details = (
                    f"No video to save (warning)\n"
                    f"Input: {input_info}\n"
                    f"Requested filename: {output_file}\n"
                    f"Result: No file created"
                )

                self._set_status_results(was_successful=True, result_details=f"{status}: {result_details}")

            case SaveVideoStatus.SUCCESS:
                # Include download information if available
                if downloaded_from_url:
                    details = f"Downloaded from {downloaded_from_url}, then {details}"

                result_details = (
                    f"Video saved successfully\n"
                    f"Input: {input_info}\n"
                    f"Requested filename: {output_file}\n"
                    f"Saved to: {saved_path}"
                )

                # Add download info to result details if available
                if downloaded_from_url:
                    result_details = f"Downloaded from: {downloaded_from_url}\n{result_details}"

                self._set_status_results(was_successful=True, result_details=f"{status}: {result_details}")

    def _handle_error_with_graceful_exit(
        self, error_details: str, exception: Exception, input_info: str, output_file: str
    ) -> None:
        """Handle error with graceful exit if failure output is connected."""
        self._handle_execution_result(
            status=SaveVideoStatus.FAILURE,
            saved_path="",
            input_info=input_info,
            output_file=output_file,
            details=error_details,
            exception=exception,
        )
        # Use the helper to handle exception based on connection status
        self._handle_failure_exception(RuntimeError(error_details))

    def _save_to_filesystem(
        self, video_bytes: bytes, output_path: Path, *, allow_creating_folders: bool, overwrite_existing: bool
    ) -> str:
        """Save video directly to filesystem at the specified absolute path."""
        # Check if file exists and overwrite is disabled
        if output_path.exists() and not overwrite_existing:
            error_details = f"File already exists and overwrite_existing is disabled: {output_path}"
            raise RuntimeError(error_details)

        # Handle parent directory creation
        if allow_creating_folders:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                error_details = f"Failed to create directory structure for path: {e!s}"
                raise RuntimeError(error_details) from e
        elif not output_path.parent.exists():
            error_details = (
                f"Parent directory does not exist and allow_creating_folders is disabled: {output_path.parent}"
            )
            raise RuntimeError(error_details)

        # Write video bytes directly to file
        try:
            output_path.write_bytes(video_bytes)
        except Exception as e:
            error_details = f"Failed to write video file to filesystem: {e!s}"
            raise RuntimeError(error_details) from e

        return str(output_path)

    def _save_to_static_storage(self, video_bytes: bytes, output_file: str, *, overwrite_existing: bool) -> str:
        """Save video using the static file manager."""
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
                error_details = (
                    f"File already exists in static storage and overwrite_existing is disabled: {output_file}"
                )
                raise RuntimeError(error_details)

        # Save to static storage
        try:
            return GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, output_file)
        except Exception as e:
            error_details = f"Failed to save video to static storage: {e!s}"
            raise RuntimeError(error_details) from e

    def _validate_video_bytes(self, video_bytes: Any) -> None:
        """Validate that video bytes are not empty."""
        if not video_bytes:
            error_message = "Video artifact contains no data"
            raise RuntimeError(error_message)
