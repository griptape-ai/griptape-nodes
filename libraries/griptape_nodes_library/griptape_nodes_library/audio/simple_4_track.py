import contextlib
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_audio import ParameterAudio
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlRequest,
    CreateStaticFileDownloadUrlResultFailure,
    CreateStaticFileDownloadUrlResultSuccess,
    CreateStaticFileUploadUrlRequest,
    CreateStaticFileUploadUrlResultFailure,
    CreateStaticFileUploadUrlResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact
from griptape_nodes_library.utils.file_utils import generate_filename


class Simple4Track(SuccessFailureNode):
    """Simple 4-Track Audio Mixer.

    A professional 4-track audio mixer with individual volume controls for each track.
    Perfect for creating podcasts, music mixes, or any multi-track audio project.

    Key Features:
    - 4 dedicated audio tracks with individual controls
    - Volume control (0.0 to 1.0) for each track
    - Mix mode: combine all tracks simultaneously
    - Professional audio processing with ffmpeg
    - Organized UI with collapsible track groups

    Use Cases:
    - Podcast production (voice + music + effects)
    - Music mixing and mastering
    - Multi-track audio projects
    - Sound design and audio post-production

    Track Layout:
    - Track 1: Primary audio (voice, main content)
    - Track 2: Secondary audio (background music, effects)
    - Track 3: Additional layer (ambient, sound effects)
    - Track 4: Final layer (intro/outro, transitions)
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        """Initialize the Simple4Track mixer with organized track groups.

        This method sets up 4 track groups, each containing audio input, volume, and pan controls.
        Tracks 1 & 2 are expanded by default, tracks 3 & 4 start collapsed for clean UI.
        """
        super().__init__(name, metadata)
        logger.debug(f"{self.name}: Initializing 4-track mixer")

        with ParameterGroup(name="Audio_Tracks") as audio_tracks_group:
            ParameterAudio(name="track1_audio")
            ParameterAudio(name="track2_audio")
            ParameterAudio(name="track3_audio")
            ParameterAudio(name="track4_audio")
        self.add_node_element(audio_tracks_group)

        with ParameterGroup(name="Volume_Controls") as volume_controls_group:
            ParameterFloat(name="track1_volume", default_value=1.0, slider=True)
            ParameterFloat(name="track2_volume", default_value=0.5, slider=True)
            ParameterFloat(name="track3_volume", default_value=0.3, slider=True)
            ParameterFloat(name="track4_volume", default_value=0.3, slider=True)
        self.add_node_element(volume_controls_group)

        # Output settings
        self.output_format = Parameter(
            name="output_format",
            type="str",
            allowed_modes={ParameterMode.PROPERTY},
            default_value="mp3",
            tooltip="Output audio format",
            traits={Options(choices=["mp3", "wav", "flac", "aac", "ogg"])},
        )
        self.add_parameter(self.output_format)

        self.quality = Parameter(
            name="quality",
            type="str",
            allowed_modes={ParameterMode.PROPERTY},
            default_value="high",
            tooltip="Audio quality setting",
            traits={Options(choices=["low", "medium", "high", "lossless"])},
        )
        self.add_parameter(self.quality)

        # Output parameter for the mixed audio
        self.mixed_audio = Parameter(
            name="mixed_audio",
            type="AudioUrlArtifact",
            allowed_modes={ParameterMode.OUTPUT},
            default_value=None,
            tooltip="The mixed audio output",
            ui_options={"pulse_on_run": True},
        )
        self.add_parameter(self.mixed_audio)

        # Add status parameters for success/failure feedback
        self._create_status_parameters(
            result_details_tooltip="Details about the 4-track mixing result",
            result_details_placeholder="Details on the audio mixing will be presented here.",
            parameter_group_initially_collapsed=False,
        )

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

        logger.debug(f"{self.name}: Called for 4-track mixing")

        # FAILURE CASES FIRST - Attempt to mix audio tracks
        try:
            self._mix_4_tracks()
        except Exception as e:
            error_details = f"Failed to mix 4 tracks: {e}"
            failure_details = f"FAILURE: {error_details}"
            self._set_status_results(was_successful=False, result_details=failure_details)
            logger.error(f"{self.name}: {error_details}")
            self._handle_failure_exception(e)
            return
        else:
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
                active_tracks.append(
                    {
                        "audio": audio,
                        "volume": volume if volume is not None else 1.0,
                        "track_num": i,
                    }
                )

        # Check if we have at least one track with audio
        if not active_tracks:
            error_msg = "At least one track must have audio input"
            raise ValueError(error_msg)

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
        try:
            response = httpx.get(audio_artifact.value, timeout=60)
            response.raise_for_status()

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
                temp_file.write(response.content)
                temp_file_path = Path(temp_file.name)

            return temp_file_path
        except Exception as e:
            error_msg = f"Failed to download audio file {index + 1}: {e}"
            raise RuntimeError(error_msg) from e

    def _mix_with_ffmpeg(self, temp_files: list[Path], track_settings: list[dict]) -> Path:
        """Mix audio files using ffmpeg with volume and pan controls."""
        # Generate output filename
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as output_file:
            output_path = Path(output_file.name)

        try:
            cmd = self._build_ffmpeg_command(temp_files, track_settings, output_path)
            self._run_ffmpeg_command(cmd)
            return output_path
        except Exception as e:
            # Clean up output file on error
            with contextlib.suppress(Exception):
                output_path.unlink()
            error_msg = f"Failed to mix audio with ffmpeg: {e}"
            raise RuntimeError(error_msg) from e

    def _build_ffmpeg_command(self, temp_files: list[Path], track_settings: list[dict], output_path: Path) -> list[str]:
        """Build the ffmpeg command for mixing audio tracks."""
        cmd = ["ffmpeg", "-y"]  # -y to overwrite output file

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
        """Build the filter_complex string for ffmpeg."""
        filter_parts = []
        for i, settings in enumerate(track_settings):
            volume = settings["volume"]

            # Apply volume filter - use acopy for audio streams
            if volume != 1.0:
                filter_parts.append(f"[{i}:a]volume={volume}[v{i}]")
            else:
                filter_parts.append(f"[{i}:a]acopy[v{i}]")

        # Mix all the volume-adjusted tracks - use same pattern as working combine_audio.py
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
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            error_msg = f"ffmpeg failed: {result.stderr}"
            raise RuntimeError(error_msg)

    def _upload_mixed_audio(self, mixed_file: Path) -> AudioUrlArtifact:
        """Upload the mixed audio file to static storage."""
        # Read the mixed audio file
        with mixed_file.open("rb") as f:
            audio_data = f.read()

        # Generate filename
        filename = generate_filename(
            node_name=self.name,
            suffix="_4track_mix",
            extension="mp3",
        )

        # Create upload URL request
        upload_request = CreateStaticFileUploadUrlRequest(file_name=filename)
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            error_msg = f"Failed to create upload URL: {upload_result.error}"
            raise RuntimeError(error_msg)

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            error_msg = f"Unexpected upload result type: {type(upload_result).__name__}"
            raise TypeError(error_msg)

        # Upload the audio data
        try:
            response = httpx.request(
                upload_result.method,
                upload_result.url,
                content=audio_data,
                headers=upload_result.headers,
                timeout=60,
            )
            response.raise_for_status()
        except Exception as e:
            error_msg = f"Failed to upload mixed audio: {e}"
            raise RuntimeError(error_msg) from e

        # Get download URL
        download_request = CreateStaticFileDownloadUrlRequest(file_name=filename)
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            error_msg = f"Failed to create download URL: {download_result.error}"
            raise RuntimeError(error_msg)

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            error_msg = f"Unexpected download result type: {type(download_result).__name__}"
            raise TypeError(error_msg)

        # Create and return AudioUrlArtifact
        return AudioUrlArtifact(value=download_result.url)

    def _get_success_message(self) -> str:
        """Generate success message with mixing details."""
        try:
            active_tracks = 0
            for i in range(1, 5):
                audio = self.get_parameter_value(f"track{i}_audio")
                if audio is not None:
                    active_tracks += 1

            return f"Successfully mixed {active_tracks} active tracks with volume controls"
        except Exception as e:
            logger.warning(f"{self.name}: Error getting mixing details: {e}")
        return "Successfully mixed 4-track audio"

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["mixed_audio"] = None
