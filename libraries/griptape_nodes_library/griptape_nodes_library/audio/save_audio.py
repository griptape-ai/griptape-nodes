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
from griptape_nodes_library.utils.audio_utils import (
    SUPPORTED_AUDIO_EXTENSIONS,
    download_audio_to_temp_file,
    extract_url_from_audio_object,
    is_audio_url_artifact,
    is_downloadable_audio_url,
)

DEFAULT_FILENAME = "griptape_nodes.mp3"


@dataclass
class AudioInput:
    """Normalized audio input - single source of truth."""

    data: bytes | None = None  # Audio bytes (if we have them)
    source_url: str | None = None  # URL to download (if we need to)
    format_hint: str | None = None  # Format from source

    @property
    def needs_download(self) -> bool:
        """True if we need to download from URL."""
        return self.source_url is not None and self.data is None


class DownloadedAudioArtifact:
    """Simple artifact for downloaded audio bytes."""

    def __init__(self, value: bytes, detected_format: str | None = None):
        self.value = value
        self.detected_format = detected_format


class SaveAudio(SuccessFailureNode):
    """Save a audio to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add audio input parameter
        self.add_parameter(
            Parameter(
                name="audio",
                input_types=["AudioArtifact", "AudioUrlArtifact"],
                type="AudioUrlArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The audio to save to file",
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
                tooltip="The output filename. The file extension will be auto-determined from audio format.",
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
            result_details_tooltip="Details about the audio save operation result",
            result_details_placeholder="Details on the save attempt will be presented here.",
        )

    def _get_audio_extension(self, audio_value: Any) -> str | None:
        """Extract and return the file extension from audio data."""
        if audio_value is None:
            return None

        # Try to extract extension from any AudioUrlArtifact URL
        if is_audio_url_artifact(audio_value) and isinstance(audio_value.value, str):
            url = audio_value.value
            filename_from_url = url.split("/")[-1].split("?")[0]
            if "." in filename_from_url:
                return Path(filename_from_url).suffix

        # Try to get extension from dict representation
        elif isinstance(audio_value, dict) and "name" in audio_value:
            filename = audio_value["name"]
            if "." in filename:
                return Path(filename).suffix

        return None

    def after_incoming_connection(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> None:
        """Handle automatic extension detection when audio connection is made."""
        if target_parameter.name == "audio":
            # Get audio value from the source node
            audio_value = source_node.parameter_output_values.get(source_parameter.name)
            if audio_value is None:
                audio_value = source_node.parameter_values.get(source_parameter.name)

            extension = self._get_audio_extension(audio_value)
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
            if f".{extension.lower()}" in SUPPORTED_AUDIO_EXTENSIONS:
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

        # Check for detected_format (our DownloadedAudioArtifact)
        if hasattr(artifact, "detected_format"):
            detected_format = artifact.detected_format  # type: ignore[attr-defined]
            if isinstance(detected_format, str):
                return detected_format

        return None

    def _normalize_input(self, raw_input: Any) -> AudioInput:
        """Convert ANY input to AudioInput. Single source of truth for input handling."""
        if not raw_input:
            return AudioInput()

        # Check if input contains a downloadable URL (handles all URL cases)
        if is_downloadable_audio_url(raw_input):
            url = extract_url_from_audio_object(raw_input)
            if url:
                return AudioInput(source_url=url, format_hint=self._extract_format_from_url(url))

        # Handle all other cases - try to extract bytes and format
        audio_bytes = self._extract_bytes_from_artifact(raw_input)
        format_hint = self._extract_format_from_artifact(raw_input)

        return AudioInput(data=audio_bytes, format_hint=format_hint)

    async def _download_audio(self, audio_input: AudioInput) -> AudioInput:
        """Download audio from URL, return AudioInput with data populated."""
        if not audio_input.source_url:
            msg = "No source URL provided for download"
            raise ValueError(msg)

        # Update status to show download starting
        self._set_status_results(
            was_successful=True, result_details=f"Downloading audio from URL: {audio_input.source_url}"
        )

        # Download to temp file
        download_result = await download_audio_to_temp_file(audio_input.source_url)

        try:
            # Update status to show download completed
            file_size = download_result.temp_file_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            self._set_status_results(
                was_successful=True,
                result_details=f"Downloaded audio ({size_mb:.1f}MB) to temporary file, processing...",
            )

            # Read audio bytes from temp file
            audio_bytes = download_result.temp_file_path.read_bytes()

            return AudioInput(
                data=audio_bytes,
                source_url=audio_input.source_url,
                format_hint=download_result.detected_format or audio_input.format_hint,
            )

        finally:
            # Always cleanup temp file
            if download_result.temp_file_path.exists():
                download_result.temp_file_path.unlink(missing_ok=True)

    def _save_audio_bytes(self, audio_bytes: bytes, format_hint: str | None) -> str:
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
                audio_bytes=audio_bytes,
                output_path=output_path,
                allow_creating_folders=allow_creating_folders,
                overwrite_existing=overwrite_existing,
            )
        # Relative path: use static file manager
        return self._save_to_static_storage_direct(
            audio_bytes=audio_bytes, output_file=output_file, overwrite_existing=overwrite_existing
        )

    def _report_warning(self, _message: str) -> None:
        """Report warning status."""
        output_file = self.get_parameter_value("output_path") or DEFAULT_FILENAME
        self.parameter_output_values["output_path"] = output_file

        result_details = (
            f"No audio to save (warning)\n"
            f"Input: No audio input\n"
            f"Requested filename: {output_file}\n"
            f"Result: No file created"
        )

        self._set_status_results(was_successful=True, result_details=f"WARNING: {result_details}")

    def _report_success(self, saved_path: str, downloaded_from_url: str | None) -> None:
        """Report success with download info if applicable."""
        output_file = self.get_parameter_value("output_path") or DEFAULT_FILENAME

        result_details = f"Audio saved successfully\nRequested filename: {output_file}\nSaved to: {saved_path}"

        # Add download info if available
        if downloaded_from_url:
            result_details = f"Downloaded from: {downloaded_from_url}\n{result_details}"

        self._set_status_results(was_successful=True, result_details=f"SUCCESS: {result_details}")
        logger.info(f"Saved audio: {saved_path}")

    def _report_error(self, error_details: str, exception: Exception | None = None) -> None:
        """Report error status."""
        failure_details = f"Audio save failed\nError: {error_details}"

        if exception:
            failure_details += f"\nException type: {type(exception).__name__}"
            if exception.__cause__:
                failure_details += f"\nCause: {exception.__cause__}"

        self._set_status_results(was_successful=False, result_details=f"FAILURE: {failure_details}")
        logger.error(f"Error saving audio: {error_details}")

        # Use the helper to handle exception based on connection status
        self._handle_failure_exception(RuntimeError(error_details))

    def _save_to_filesystem_direct(
        self, audio_bytes: bytes, output_path: Path, *, allow_creating_folders: bool, overwrite_existing: bool
    ) -> str:
        """Save audio bytes directly to filesystem at the specified absolute path."""
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

        # Write audio bytes directly to file
        output_path.write_bytes(audio_bytes)
        return str(output_path)

    def _save_to_static_storage_direct(self, audio_bytes: bytes, output_file: str, *, overwrite_existing: bool) -> str:
        """Save audio bytes using the static file manager."""
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
        return GriptapeNodes.StaticFilesManager().save_static_file(audio_bytes, output_file)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = []

        # Validate that we have a audio.
        audio = self.parameter_values.get("audio")
        if not audio:
            exceptions.append(ValueError("Audio parameter is required"))

        return exceptions if exceptions else None

    async def aprocess(self) -> None:
        """Async process method - linear pipeline approach."""
        # Reset execution state at the very top
        self._clear_execution_status()

        try:
            # Step 1: Normalize input (handles ALL artifact types)
            audio_input = self._normalize_input(self.get_parameter_value("audio"))

            # Step 2: Download if needed (simple conditional)
            if audio_input.needs_download:
                audio_input = await self._download_audio(audio_input)

            # Step 3: Validate we have data
            if not audio_input.data:
                self._report_warning("No audio data available")
                return

            # Step 4: Save audio bytes
            saved_path = self._save_audio_bytes(audio_input.data, audio_input.format_hint)

            # Step 5: Report success
            self._report_success(saved_path, audio_input.source_url)

        except Exception as e:
            self._report_error(str(e), e)

    def process(self) -> None:
        """Sync process method - handles non-URL audios only."""
        # Reset execution state and result details at the start of each run
        self._clear_execution_status()

        try:
            # Step 1: Normalize input
            audio_input = self._normalize_input(self.get_parameter_value("audio"))

            # Step 2: Check if we need async download (not supported in sync)
            if audio_input.needs_download:
                self._report_error(
                    "URL audio downloads require async processing. This should not happen in normal operation."
                )
                return

            # Step 3: Validate we have data
            if not audio_input.data:
                self._report_warning("No audio data available")
                return

            # Step 4: Save audio bytes
            saved_path = self._save_audio_bytes(audio_input.data, audio_input.format_hint)

            # Step 5: Report success
            self._report_success(saved_path, None)

        except Exception as e:
            self._report_error(str(e), e)
