import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from griptape.artifacts import AudioArtifact
from griptape.artifacts.audio_url_artifact import AudioUrlArtifact

from griptape_nodes.exe_types.core_types import ParameterGroup
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_audio import ParameterAudio
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import logger


class AudioDetails(DataNode):
    """Extract detailed information from an audio file including duration, format, bitrate, and sample rate."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input parameter for the audio
        self.add_parameter(
            ParameterAudio(
                name="audio",
                default_value=value,
                tooltip="The audio file to analyze",
                allow_output=False,
                hide_property=True,
            )
        )

        # Basic Info group (default open)
        with ParameterGroup(name="Basic Info") as basic_group:
            self._duration_parameter = ParameterFloat(
                name="duration",
                default_value=0.0,
                tooltip="Audio duration in seconds",
                allow_input=False,
                allow_property=False,
                settable=False,
            )

            self._format_parameter = ParameterString(
                name="format",
                default_value="UNKNOWN",
                tooltip="Audio format (e.g., 'mp3', 'wav', 'ogg')",
                allow_input=False,
                allow_property=False,
                settable=False,
            )

            self._file_size_parameter = ParameterInt(
                name="file_size",
                default_value=0,
                tooltip="File size in bytes",
                allow_input=False,
                allow_property=False,
                settable=False,
            )
        self.add_node_element(basic_group)

        # Audio Properties group (collapsed by default)
        with ParameterGroup(name="Audio Properties", ui_options={"collapsed": True}) as properties_group:
            self._sample_rate_parameter = ParameterInt(
                name="sample_rate",
                default_value=0,
                tooltip="Sample rate in Hz",
                allow_input=False,
                allow_property=False,
                settable=False,
            )

            self._channels_parameter = ParameterInt(
                name="channels",
                default_value=0,
                tooltip="Number of audio channels",
                allow_input=False,
                allow_property=False,
                settable=False,
            )

            self._bitrate_parameter = ParameterInt(
                name="bitrate",
                default_value=0,
                tooltip="Audio bitrate in bits per second",
                allow_input=False,
                allow_property=False,
                settable=False,
            )

            self._codec_parameter = ParameterString(
                name="codec",
                default_value="UNKNOWN",
                tooltip="Audio codec (e.g., 'mp3', 'aac', 'pcm')",
                allow_input=False,
                allow_property=False,
                settable=False,
            )
        self.add_node_element(properties_group)

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Override to update outputs immediately when audio parameter is set."""
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        if param_name == "audio":
            self._update_audio_details(value)

    def _update_audio_details(self, audio: AudioUrlArtifact | AudioArtifact | None) -> None:
        """Update all output values based on the audio."""
        # FAILURE CASES FIRST
        if audio is None:
            self._set_default_values()
            return

        # Get audio URL
        audio_url = self._get_audio_url(audio)
        if not audio_url:
            self._set_default_values()
            return

        # Analyze audio with ffprobe
        audio_info = self._analyze_audio_with_ffprobe(audio_url)
        if not audio_info:
            self._set_default_values()
            return

        # SUCCESS PATH AT END - Set all output values
        self.parameter_output_values["duration"] = audio_info.get("duration", 0.0)
        self.parameter_output_values["format"] = audio_info.get("format", "UNKNOWN")
        self.parameter_output_values["file_size"] = audio_info.get("file_size", 0)
        self.parameter_output_values["sample_rate"] = audio_info.get("sample_rate", 0)
        self.parameter_output_values["channels"] = audio_info.get("channels", 0)
        self.parameter_output_values["bitrate"] = audio_info.get("bitrate", 0)
        self.parameter_output_values["codec"] = audio_info.get("codec", "UNKNOWN")

    def process(self) -> None:
        """Extract and output all audio details.

        Note: The actual extraction happens in set_parameter_value when the audio
        parameter is set, so this method just refreshes the outputs.
        """
        audio = self.get_parameter_value("audio")
        self._update_audio_details(audio)

    def _get_audio_url(self, audio: AudioUrlArtifact | AudioArtifact) -> str | None:
        """Extract URL from audio artifact or save bytes to temp file."""
        # FAILURE CASES FIRST
        if not audio:
            return None

        if isinstance(audio, AudioUrlArtifact):
            return audio.value

        if isinstance(audio, AudioArtifact):
            # For AudioArtifact with bytes, save to temp file and return path
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
                    temp_file.write(audio.value)
                    return str(Path(temp_file.name).absolute())
            except Exception as e:
                logger.error(f"{self.name}: Failed to create temp file for AudioArtifact: {e}")
                return None

        if isinstance(audio, dict) and "value" in audio:
            return audio["value"]

        return None

    def _analyze_audio_with_ffprobe(self, audio_url: str) -> dict[str, Any] | None:  # noqa: PLR0911
        """Analyze audio file using ffprobe to extract detailed information."""
        # FAILURE CASES FIRST
        try:
            # Get ffprobe path
            ffprobe_path = self._get_ffprobe_path()
        except Exception as e:
            logger.error(f"{self.name}: Failed to get ffprobe path: {e}")
            return None

        try:
            # Build ffprobe command to get comprehensive audio information
            cmd = [ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", audio_url]

            # Run ffprobe command
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)  # noqa: S603
            data = json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            logger.error(f"{self.name}: ffprobe timed out analyzing audio")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(f"{self.name}: ffprobe failed: {e.stderr}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"{self.name}: Failed to parse ffprobe output: {e}")
            return None
        except Exception as e:
            logger.error(f"{self.name}: Unexpected error during audio analysis: {e}")
            return None

        # FAILURE CASES FIRST - Parse data
        try:
            # Get format information
            format_info = data.get("format", {})
            duration = float(format_info.get("duration", 0))
            file_size = int(format_info.get("size", 0))
            bitrate = int(format_info.get("bit_rate", 0))

            # Get audio stream information
            streams = data.get("streams", [])
            audio_stream = None
            for stream in streams:
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break

            if not audio_stream:
                logger.warning(f"{self.name}: No audio stream found in file")
                return None

        except (ValueError, TypeError) as e:
            logger.error(f"{self.name}: Failed to parse audio properties: {e}")
            return None

        # SUCCESS PATH AT END - Extract audio properties
        sample_rate = int(audio_stream.get("sample_rate", 0))
        channels = int(audio_stream.get("channels", 0))
        codec = audio_stream.get("codec_name", "UNKNOWN")
        format_name = format_info.get("format_name", "UNKNOWN")

        return {
            "duration": duration,
            "format": format_name,
            "file_size": file_size,
            "sample_rate": sample_rate,
            "channels": channels,
            "bitrate": bitrate,
            "codec": codec,
        }

    def _get_ffprobe_path(self) -> str:
        """Get the path to ffprobe executable."""
        # FAILURE CASES FIRST
        try:
            # Try to find ffprobe in PATH
            result = subprocess.run(["which", "ffprobe"], capture_output=True, text=True, check=True)  # noqa: S607
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            pass

        # Try common installation paths
        common_paths = [
            "/usr/bin/ffprobe",
            "/usr/local/bin/ffprobe",
            "/opt/homebrew/bin/ffprobe",
            "ffprobe",  # Fallback to PATH
        ]

        for path in common_paths:
            try:
                subprocess.run([path, "-version"], capture_output=True, text=True, check=True, timeout=5)  # noqa: S603
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                continue
            else:
                return path

        # SUCCESS PATH AT END
        error_msg = f"{self.name}: ffprobe not found. Please install FFmpeg with ffprobe."
        raise RuntimeError(error_msg)

    def _set_default_values(self) -> None:
        """Set all output values to defaults."""
        self.parameter_output_values["duration"] = 0.0
        self.parameter_output_values["format"] = "UNKNOWN"
        self.parameter_output_values["file_size"] = 0
        self.parameter_output_values["sample_rate"] = 0
        self.parameter_output_values["channels"] = 0
        self.parameter_output_values["bitrate"] = 0
        self.parameter_output_values["codec"] = "UNKNOWN"
