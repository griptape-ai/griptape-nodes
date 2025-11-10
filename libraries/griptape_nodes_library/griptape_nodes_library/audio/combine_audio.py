import contextlib
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from griptape.artifacts.audio_url_artifact import AudioUrlArtifact

from griptape_nodes.exe_types.core_types import (
    ParameterGroup,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_audio import ParameterAudio
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.ffmpeg_utils import get_ffmpeg_path
from griptape_nodes_library.utils.file_utils import generate_filename


class CombineAudio(SuccessFailureNode):
    """Simple 4-Track Audio Combiner.

    A 4-track audio mixer with individual volume controls for each track.

    Key Features:
    - 4 dedicated audio tracks with individual controls
    - Volume control (0.0 to 1.0) for each track
    - Mix mode: combine all tracks simultaneously
    - Professional audio processing with ffmpeg
    - Organized UI with collapsible track groups

    Track Layout:
    - Track 1: Primary audio (voice, main content)
    - Track 2: Secondary audio (background music, effects)
    - Track 3: Additional layer (ambient, sound effects)
    - Track 4: Final layer (intro/outro, transitions)
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        """Initialize the audio tracks."""
        super().__init__(name, metadata)

        with ParameterGroup(name="Audio_Tracks") as audio_tracks_group:
            ParameterAudio(name="track1_audio", hide_property=True)
            ParameterAudio(name="track2_audio", hide_property=True)
            ParameterAudio(name="track3_audio", hide_property=True)
            ParameterAudio(name="track4_audio", hide_property=True)
        self.add_node_element(audio_tracks_group)

        with ParameterGroup(name="Volume_Controls") as volume_controls_group:
            ParameterFloat(name="track1_volume", default_value=1.0, min_val=0.0, max_val=1.0, slider=True)
            ParameterFloat(name="track2_volume", default_value=0.5, min_val=0.0, max_val=1.0, slider=True)
            ParameterFloat(name="track3_volume", default_value=0.3, min_val=0.0, max_val=1.0, slider=True)
            ParameterFloat(name="track4_volume", default_value=0.3, min_val=0.0, max_val=1.0, slider=True)
        self.add_node_element(volume_controls_group)

        with ParameterGroup(name="Pan_Controls", collapsed=True) as pan_controls_group:
            ParameterFloat(name="track1_pan", default_value=0, min_val=-1.0, max_val=1.0, slider=True)
            ParameterFloat(name="track2_pan", default_value=0, min_val=-1.0, max_val=1.0, slider=True)
            ParameterFloat(name="track3_pan", default_value=0, min_val=-1.0, max_val=1.0, slider=True)
            ParameterFloat(name="track4_pan", default_value=0, min_val=-1.0, max_val=1.0, slider=True)
        self.add_node_element(pan_controls_group)

        # Output settings
        with ParameterGroup(name="Output_Settings", collapsed=True) as output_settings_group:
            self.output_format = ParameterString(
                name="output_format",
                allow_input=False,
                allow_output=False,
                default_value="mp3",
                tooltip="Output audio format",
                traits={Options(choices=["mp3", "wav", "flac", "aac", "ogg"])},
            )

            self.quality = ParameterString(
                name="quality",
                allow_input=False,
                allow_output=False,
                default_value="high",
                tooltip="Audio quality setting",
                traits={Options(choices=["low", "medium", "high", "lossless"])},
            )
        self.add_node_element(output_settings_group)

        # Output parameter for the mixed audio
        self.mixed_audio = ParameterAudio(
            name="mixed_audio",
            allow_input=False,
            allow_property=False,
            default_value=None,
            tooltip="The mixed audio output",
            pulse_on_run=True,
        )
        self.add_parameter(self.mixed_audio)

        # Add status parameters for success/failure feedback
        self._create_status_parameters(
            result_details_tooltip="Details about the 4-track mixing result",
            result_details_placeholder="Details on the audio mixing will be presented here.",
            parameter_group_initially_collapsed=False,
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that at least one track has audio input before running the node."""
        exceptions = []

        # Check if we have at least one track with audio
        active_tracks = 0
        for i in range(1, 5):
            audio = self.get_parameter_value(f"track{i}_audio")
            if audio is not None:
                active_tracks += 1

        if active_tracks == 0:
            exceptions.append(ValueError(f"{self.name}: At least one track must have audio input"))

        return exceptions if exceptions else None

    def process(self) -> None:
        """Process the node by mixing the 4 audio tracks.

        This is the main execution method that:
        1. Resets the execution state and sets failure defaults
        2. Attempts to mix the 4 audio tracks with volume and pan controls
        3. Handles any errors that occur during the mixing process
        4. Sets success status with detailed result information

        The method follows the SuccessFailureNode pattern with comprehensive error handling
        and status reporting for a professional user experience.
        """
        # Reset execution state and set failure defaults
        self._clear_execution_status()
        self._set_failure_output_values()

        # FAILURE CASES FIRST - Attempt to mix audio tracks
        try:
            self._mix_4_tracks()
        except Exception as e:
            error_details = f"Failed to mix 4 tracks: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            msg = f"{self.name}: {error_details}"
            logger.error(msg)
            self._handle_failure_exception(e)
            return

        # SUCCESS PATH AT END - Set success status with detailed information
        success_details = self._get_success_message()
        self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
        logger.debug(f"{self.name}: {success_details}")

    def _mix_4_tracks(self) -> None:
        """Mix the 4 audio tracks with volume and pan controls.

        This method implements the core 4-track mixing logic:
        1. Collects all track inputs, volumes, and pan settings
        2. Downloads audio files to temporary files
        3. Uses ffmpeg to mix tracks with volume and pan controls
        4. Uploads the result to static storage
        """
        # Get only tracks that have audio inputs
        active_tracks = []
        for i in range(1, 5):
            audio = self.get_parameter_value(f"track{i}_audio")
            if audio is not None:
                volume = self.get_parameter_value(f"track{i}_volume")
                pan = self.get_parameter_value(f"track{i}_pan")
                active_tracks.append(
                    {
                        "audio": audio,
                        "volume": volume if volume is not None else 1.0,
                        "pan": pan if pan is not None else 0.0,
                        "track_num": i,
                    }
                )

        logger.debug(f"{self.name}: Mixing {len(active_tracks)} active tracks")

        # Download audio files to temporary files
        temp_files = []
        track_settings = []
        try:
            for track in active_tracks:
                temp_file = self._download_audio_to_temp(track["audio"], track["track_num"] - 1)
                temp_files.append(temp_file)
                track_settings.append(
                    {
                        "volume": track["volume"],
                        "pan": track["pan"],
                    }
                )
                logger.debug(f"{self.name}: Downloaded track {track['track_num']}")

            # Mix tracks using ffmpeg
            mixed_file = self._mix_with_ffmpeg(temp_files, track_settings)
            logger.debug(f"{self.name}: Successfully mixed audio tracks")

            # Upload mixed audio to static storage
            audio_artifact = self._upload_mixed_audio(mixed_file)
            self.parameter_output_values["mixed_audio"] = audio_artifact

        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                with contextlib.suppress(Exception):
                    temp_file.unlink()

    def _download_audio_to_temp(self, audio_artifact: AudioUrlArtifact, index: int) -> Path:
        """Download an audio file to a temporary file."""
        # FAILURE CASES FIRST
        try:
            response = httpx.get(audio_artifact.value, timeout=60)
        except httpx.TimeoutException as e:
            error_msg = f"{self.name}: Failed to download audio file {index + 1}: timeout after 60 seconds"
            raise RuntimeError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"{self.name}: Failed to download audio file {index + 1}: network error - {e}"
            raise RuntimeError(error_msg) from e

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            error_msg = f"{self.name}: Failed to download audio file {index + 1}: HTTP {e.response.status_code}"
            raise RuntimeError(error_msg) from e

        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
                temp_file.write(response.content)
                temp_file_path = Path(temp_file.name)
        except OSError as e:
            error_msg = f"{self.name}: Failed to create temporary file for audio {index + 1}: {e}"
            raise RuntimeError(error_msg) from e

        # SUCCESS PATH AT END
        return temp_file_path

    def _mix_with_ffmpeg(self, temp_files: list[Path], track_settings: list[dict]) -> Path:
        """Mix audio files using ffmpeg with volume and pan controls."""
        # FAILURE CASES FIRST
        try:
            # Generate output filename
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as output_file:
                output_path = Path(output_file.name)
        except OSError as e:
            error_msg = f"{self.name}: Failed to create temporary output file: {e}"
            raise RuntimeError(error_msg) from e

        try:
            cmd = self._build_ffmpeg_command(temp_files, track_settings, output_path)
        except Exception as e:
            # Clean up output file on error
            with contextlib.suppress(Exception):
                output_path.unlink()
            error_msg = f"{self.name}: Failed to build ffmpeg command: {e}"
            raise RuntimeError(error_msg) from e

        try:
            self._run_ffmpeg_command(cmd)
        except Exception as e:
            # Clean up output file on error
            with contextlib.suppress(Exception):
                output_path.unlink()
            error_msg = f"{self.name}: Failed to run ffmpeg command: {e}"
            raise RuntimeError(error_msg) from e

        # SUCCESS PATH AT END
        return output_path

    def _build_ffmpeg_command(self, temp_files: list[Path], track_settings: list[dict], output_path: Path) -> list[str]:
        """Build the ffmpeg command for mixing audio tracks."""
        ffmpeg_path = self._get_ffmpeg_path()
        cmd = [ffmpeg_path, "-y"]  # -y to overwrite output file

        # Add all input files
        for temp_file in temp_files:
            cmd.extend(["-i", str(temp_file.absolute())])

        # Build filter_complex with volume controls
        filter_parts = self._build_filter_complex(track_settings)
        filter_complex = ";".join(filter_parts)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", "[out]"])

        # Add codec and quality settings
        self._add_codec_settings(cmd)

        cmd.append(str(output_path))
        return cmd

    def _build_filter_complex(self, track_settings: list[dict]) -> list[str]:
        """Build the filter_complex string for ffmpeg with volume and pan controls."""
        filter_parts = []
        for i, settings in enumerate(track_settings):
            volume = settings["volume"]
            pan = settings["pan"]

            # Build filter chain: volume -> pan (if needed)
            current_input = f"[{i}:a]"
            current_output = f"[v{i}]"

            # Apply volume filter
            if volume != 1.0:
                filter_parts.append(f"{current_input}volume={volume}[vol{i}]")
                current_input = f"[vol{i}]"

            # Apply pan filter (convert pan value to ffmpeg pan format)
            if pan != 0.0:
                # Convert pan from -1.0 to 1.0 to ffmpeg pan format
                # pan=1.0: hard right (left=0, right=1)
                # pan=-1.0: hard left (left=1, right=0)
                # pan=0.0: center (left=1, right=1)

                # Calculate gains for proper stereo panning
                if pan > 0:  # Panning right
                    left_gain = 1.0 - pan  # Reduce left as pan increases
                    right_gain = 1.0  # Keep right at full
                else:  # Panning left
                    left_gain = 1.0  # Keep left at full
                    right_gain = 1.0 + pan  # Reduce right as pan becomes more negative

                # FFmpeg pan filter: left channel gets left_gain*L, right channel gets right_gain*R
                pan_filter = f"pan=stereo|c0={left_gain:.3f}*c0|c1={right_gain:.3f}*c1"
                filter_parts.append(f"{current_input}{pan_filter}{current_output}")
            else:
                # No pan needed, just copy
                filter_parts.append(f"{current_input}acopy{current_output}")

        # Mix all the processed tracks
        if len(track_settings) == 1:
            # Single track - just use the processed track directly
            filter_parts.append("[v0]acopy[out]")
        else:
            # Multiple tracks - mix them together
            volume_inputs = "".join([f"[v{i}]" for i in range(len(track_settings))])
            filter_parts.append(f"{volume_inputs}amix=inputs={len(track_settings)}:duration=longest[out]")
        return filter_parts

    def _add_codec_settings(self, cmd: list[str]) -> None:
        """Add codec and quality settings to the ffmpeg command."""
        output_format = self.get_parameter_value("output_format")
        quality = self.get_parameter_value("quality")

        if output_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame"])
        elif output_format == "wav":
            cmd.extend(["-c:a", "pcm_s16le"])

        # Add quality settings
        if quality == "high":
            cmd.extend(["-b:a", "320k"])
        elif quality == "medium":
            cmd.extend(["-b:a", "192k"])
        elif quality == "low":
            cmd.extend(["-b:a", "128k"])

    def _run_ffmpeg_command(self, cmd: list[str]) -> None:
        """Run the ffmpeg command and handle errors."""
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=300)  # noqa: S603
        if result.returncode != 0:
            error_msg = f"{self.name}: ffmpeg failed: {result.stderr}"
            raise RuntimeError(error_msg)

    def _upload_mixed_audio(self, mixed_file: Path) -> AudioUrlArtifact:
        """Upload the mixed audio file to static storage."""
        # FAILURE CASES FIRST
        try:
            # Read the mixed audio file
            with mixed_file.open("rb") as f:
                audio_data = f.read()
        except OSError as e:
            error_msg = f"{self.name}: Failed to read mixed audio file: {e}"
            raise RuntimeError(error_msg) from e

        # Generate filename
        filename = generate_filename(
            node_name=self.name,
            suffix="_4track_mix",
            extension="mp3",
        )

        try:
            # Use the simple static file manager pattern like other audio nodes
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(audio_data, filename)
        except Exception as e:
            error_msg = f"{self.name}: Failed to save mixed audio to static storage: {e}"
            raise RuntimeError(error_msg) from e

        # SUCCESS PATH AT END
        return AudioUrlArtifact(value=saved_url)

    def _get_success_message(self) -> str:
        """Generate success message with mixing details."""
        try:
            active_tracks = 0
            for i in range(1, 5):
                audio = self.get_parameter_value(f"track{i}_audio")
                if audio is not None:
                    active_tracks += 1

        except Exception as e:
            logger.warning(f"{self.name}: Error getting mixing details: {e}")
            return "Successfully mixed 4-track audio"
        else:
            return f"Successfully mixed {active_tracks} active tracks with volume controls"

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["mixed_audio"] = None

    def _get_ffmpeg_path(self) -> str:
        """Get the path to ffmpeg executable using the common utility."""
        try:
            return get_ffmpeg_path()
        except Exception as e:
            error_msg = f"{self.name}: {e}"
            raise RuntimeError(error_msg) from e
