import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact
from griptape_nodes_library.utils.audio_utils import (
    detect_audio_format,
    to_audio_artifact,
    validate_url,
)
from griptape_nodes_library.utils.file_utils import generate_filename


class BaseAudioProcessor(SuccessFailureNode, ABC):
    """Base class for audio processing nodes with common functionality."""

    # Default audio properties constants
    DEFAULT_QUALITY = "high"
    DEFAULT_SAMPLE_RATE = 44100

    # Common audio format options
    AUDIO_FORMAT_OPTIONS: ClassVar[dict[str, str]] = {
        "auto": "Auto (preserve input format)",
        "mp3": "MP3 (widely compatible, good compression)",
        "wav": "WAV (uncompressed, highest quality)",
        "aac": "AAC (good compression, modern standard)",
        "flac": "FLAC (lossless compression)",
        "ogg": "OGG (open-source alternative)",
        "m4a": "M4A (Apple's audio format)",
    }

    # Audio quality options for lossy formats
    AUDIO_QUALITY_OPTIONS: ClassVar[dict[str, str]] = {
        "low": "Low (64k bitrate)",
        "medium": "Medium (96k bitrate)",
        "high": "High (128k bitrate)",
        "very_high": "Very High (192k bitrate)",
        "copy": "Copy (preserve original quality)",
    }

    # Sample rate options
    SAMPLE_RATE_OPTIONS: ClassVar[dict[str, str]] = {
        "auto": "Auto (preserve input sample rate)",
        "8000": "8 kHz (telephone quality)",
        "16000": "16 kHz (voice quality)",
        "22050": "22.05 kHz (low quality)",
        "44100": "44.1 kHz (CD quality)",
        "48000": "48 kHz (professional audio)",
        "96000": "96 kHz (high-resolution audio)",
    }

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add audio input parameter
        self.add_parameter(
            Parameter(
                name="input_audio",
                input_types=["AudioUrlArtifact", "AudioArtifact", "str"],
                type="AudioUrlArtifact",
                tooltip="The audio to process (can be AudioUrlArtifact or URL string)",
                ui_options={
                    "clickable_file_browser": True,
                },
            )
        )

        self._setup_custom_parameters()

        # Add output format parameter
        format_param = Parameter(
            name="output_format",
            type="str",
            default_value="auto",
            tooltip="Output audio format. Choose 'auto' to preserve input format, or select a specific format.",
        )
        format_param.add_trait(Options(choices=list(self.AUDIO_FORMAT_OPTIONS.keys())))
        self.add_parameter(format_param)

        # Add quality parameter for lossy formats
        quality_param = Parameter(
            name="quality",
            type="str",
            default_value=self.DEFAULT_QUALITY,
            tooltip="Audio quality for lossy formats",
        )
        quality_param.add_trait(Options(choices=list(self.AUDIO_QUALITY_OPTIONS.keys())))
        self.add_parameter(quality_param)

        # Add sample rate parameter
        sample_rate_param = Parameter(
            name="sample_rate",
            type="str",
            default_value="auto",
            tooltip="Output sample rate. Choose 'auto' to preserve input sample rate.",
        )
        sample_rate_param.add_trait(Options(choices=list(self.SAMPLE_RATE_OPTIONS.keys())))
        self.add_parameter(sample_rate_param)

        # Add output parameter
        self.add_parameter(
            Parameter(
                name="output",
                output_type="AudioUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The processed audio",
                ui_options={"pulse_on_run": True, "expander": True},
            )
        )

        # Add status parameters using the SuccessFailureNode helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the audio processing result",
            result_details_placeholder="Details on the audio processing will be presented here.",
            parameter_group_initially_collapsed=True,
        )

        self._setup_logging_group()

    @abstractmethod
    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters specific to this audio processor. Override in subclasses."""

    @abstractmethod
    def _get_processing_description(self) -> str:
        """Get a description of what this processor does. Override in subclasses."""

    @abstractmethod
    def _process_audio_with_ffmpeg(self, input_path: str, output_path: str, **kwargs) -> None:
        """Process the audio using FFmpeg. Override in subclasses."""

    def _setup_logging_group(self) -> None:
        """Setup the common logging parameter group."""
        with ParameterGroup(name="Logs") as logs_group:
            Parameter(
                name="logs",
                type="str",
                tooltip="Displays processing logs and detailed events if enabled.",
                ui_options={"multiline": True, "placeholder_text": "Logs"},
                allowed_modes={ParameterMode.OUTPUT},
            )
        logs_group.ui_options = {"hide": True}  # Hide the logs group by default
        self.add_node_element(logs_group)

    def _validate_audio_input(self) -> list[Exception] | None:
        """Common audio input validation."""
        exceptions = []

        # Only validate if there's actually a value to validate
        audio = self.parameter_values.get("input_audio")
        if audio is not None:
            # Convert to audio artifact to normalize the input
            try:
                audio_artifact = to_audio_artifact(audio)
                if not hasattr(audio_artifact, "value") or not audio_artifact.value:
                    msg = f"{self.name}: Input audio parameter must have a valid value"
                    exceptions.append(ValueError(msg))
                else:
                    # Validate URL safety
                    try:
                        self._validate_url_safety(audio_artifact.value)
                    except ValueError as e:
                        exceptions.append(e)
            except Exception as e:
                msg = f"{self.name}: Invalid audio input: {e}"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _validate_url_safety(self, url: str) -> None:
        """Validate that the URL is safe for ffmpeg processing."""
        if not validate_url(url):
            msg = f"{self.name}: Invalid or unsafe URL provided: {url}"
            raise ValueError(msg)

    def _get_audio_input_data(self) -> tuple[str, str]:
        """Get audio input URL and detected format."""
        audio = self.parameter_values.get("input_audio")
        audio_artifact = to_audio_artifact(audio)
        input_url = audio_artifact.value

        detected_format = detect_audio_format(audio)
        if not detected_format:
            detected_format = "mp3"  # default fallback

        return input_url, detected_format

    def _get_output_format(self, input_format: str) -> str:
        """Get the output format based on user preference."""
        output_format = self.get_parameter_value("output_format") or "auto"

        if output_format == "auto":
            return input_format

        return output_format

    def _get_quality_setting(self) -> str:
        """Get the quality setting for lossy formats."""
        quality_value = self.get_parameter_value("quality")
        if quality_value is None:
            return self.DEFAULT_QUALITY
        return quality_value

    def _get_sample_rate_setting(self) -> str:
        """Get the sample rate setting."""
        sample_rate_value = self.get_parameter_value("sample_rate")
        if sample_rate_value is None:
            return "auto"
        return sample_rate_value

    def _create_temp_output_file(self, format_extension: str) -> tuple[str, Path]:
        """Create a temporary output file and return path."""
        with tempfile.NamedTemporaryFile(suffix=f".{format_extension.lower()}", delete=False) as output_file:
            output_path = Path(output_file.name)
        return str(output_path), output_path

    def _save_audio_artifact(self, audio_path: str, format_extension: str, suffix: str = "") -> AudioUrlArtifact:
        """Save audio file to static file and return AudioUrlArtifact."""
        # Generate meaningful filename based on workflow and node
        filename = self._generate_filename(suffix, format_extension)

        # Read the audio file
        with Path(audio_path).open("rb") as f:
            audio_bytes = f.read()

        # Save to static file with our custom filename
        url = GriptapeNodes.StaticFilesManager().save_static_file(audio_bytes, filename)
        return AudioUrlArtifact(url)

    def _cleanup_temp_file(self, file_path: Path) -> None:
        """Clean up temporary file with error handling."""
        try:
            file_path.unlink(missing_ok=True)
        except Exception as e:
            self.append_value_to_parameter("logs", f"Warning: Failed to clean up temporary file: {e}\n")

    def _log_audio_properties(self, audio_url: str) -> None:
        """Log detected audio properties."""
        # For now, just log the URL. In a real implementation, you might use ffprobe
        # to get detailed audio information
        self.append_value_to_parameter("logs", f"Processing audio URL: {audio_url}\n")

    def _log_format_detection(self, detected_format: str) -> None:
        """Log detected audio format."""
        self.append_value_to_parameter("logs", f"Detected audio format: {detected_format}\n")

    def validate_before_node_run(self) -> list[Exception] | None:
        """Common audio input validation."""
        exceptions = []

        # Use base class validation for audio input
        base_exceptions = self._validate_audio_input()
        if base_exceptions:
            exceptions.extend(base_exceptions)

        # Add custom validation from subclasses
        custom_exceptions = self._validate_custom_parameters()
        if custom_exceptions:
            exceptions.extend(custom_exceptions)

        # If there are validation errors, set the status to failure
        if exceptions:
            error_messages = [str(e) for e in exceptions]
            error_details = f"Validation failed: {'; '.join(error_messages)}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")

        return exceptions if exceptions else None

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate custom parameters. Override in subclasses if needed."""
        return None

    def _process(self, audio_url: str, detected_format: str, **kwargs) -> None:
        """Common processing wrapper."""
        self.append_value_to_parameter("logs", f"{self._get_processing_description()}\n")

        # Get output format
        output_format = self._get_output_format(detected_format)

        # Get output suffix from subclass
        suffix = self._get_output_suffix(**kwargs)

        # Create temporary output file
        output_path, output_path_obj = self._create_temp_output_file(output_format)

        try:
            # Process audio using the custom implementation
            self._process_audio_with_ffmpeg(audio_url, output_path, **kwargs)

            # Save processed audio
            output_artifact = self._save_audio_artifact(output_path, output_format, suffix)

            self.append_value_to_parameter(
                "logs", f"Successfully processed audio with suffix: {suffix}.{output_format.lower()}\n"
            )

            # Save to parameter
            self.parameter_output_values["output"] = output_artifact

        finally:
            # Clean up temporary file
            self._cleanup_temp_file(output_path_obj)

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get the output filename suffix. Override in subclasses if needed."""
        return ""

    def process(self) -> None:
        """Main workflow execution method following the image processor pattern."""
        # Reset execution state and result details at the start of each run
        self._clear_execution_status()

        # Clear output values to prevent downstream nodes from getting stale data on errors
        self.parameter_output_values["output"] = None

        # Get input audio
        input_audio = self.get_parameter_value("input_audio")

        if input_audio is None:
            error_details = "No input audio provided"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            self._handle_failure_exception(RuntimeError(error_details))
            return

        try:
            # Get audio input data
            audio_url, detected_format = self._get_audio_input_data()
            self._log_format_detection(detected_format)
            self._log_audio_properties(audio_url)

            # Get custom parameters from subclasses
            custom_params = self._get_custom_parameters()

            # Initialize logs
            self.append_value_to_parameter("logs", f"[Processing {self._get_processing_description()}..]\n")

            # Run the audio processing
            self.append_value_to_parameter("logs", "[Started audio processing..]\n")
            self._process(audio_url, detected_format, **custom_params)
            self.append_value_to_parameter("logs", "[Finished audio processing.]\n")

            # Success case
            success_details = f"Successfully processed audio: {self._get_processing_description()}"
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
            logger.info(f"{self.__class__.__name__} '{self.name}': {success_details}")

        except Exception as e:
            error_details = f"Failed to process audio: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.__class__.__name__} '{self.name}': {error_details}")
            self._handle_failure_exception(e)

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing. Override in subclasses if needed."""
        return {}

    def _generate_filename(self, suffix: str = "", extension: str = "mp3") -> str:
        """Generate a meaningful filename based on workflow and node information."""
        return generate_filename(
            node_name=self.name,
            suffix=suffix,
            extension=extension,
        )
