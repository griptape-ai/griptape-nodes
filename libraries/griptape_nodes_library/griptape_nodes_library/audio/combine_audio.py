import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
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


class CombineAudio(SuccessFailureNode):
    """Combine multiple audio tracks into a single audio file.

    This node takes a list of audio files and combines them into a single output file.
    It supports various combination modes like concatenation, mixing, and overlay.

    Key Features:
    - Combines multiple audio tracks into a single file
    - Supports concatenation (one after another) and mixing (simultaneous playback)
    - Handles different audio formats and sample rates
    - Uses ffmpeg for professional audio processing
    - Provides detailed success/failure feedback with processing statistics

    Use Cases:
    - Creating podcasts by combining intro, content, and outro
    - Mixing music tracks with sound effects
    - Creating audio playlists or compilations
    - Layering multiple audio sources for rich soundscapes

    Examples:
    - Concatenate: [intro.mp3, content.mp3, outro.mp3] → combined.mp3
    - Mix: [music.mp3, voice.mp3] → mixed.mp3 (both play simultaneously)
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        """Initialize the CombineAudio node with input/output parameters and status tracking.

        This method sets up the node's parameters for audio input list and combined output,
        along with comprehensive status tracking for professional user feedback.
        """
        super().__init__(name, metadata)
        logger.debug(f"{self.name}: Initializing node")

        # Input parameter for the list of audio files to combine
        # This accepts a ParameterList of AudioUrlArtifact objects
        self.audio_list = ParameterList(
            name="audio_list",
            input_types=["AudioUrlArtifact"],
            type="ParameterList",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=[],
            tooltip="List of audio files to combine into a single track",
            ui_options={"hide_property": False},
        )
        self.add_parameter(self.audio_list)

        # ParameterList for track volumes (0.0 to 1.0)
        # This automatically syncs with the audio_list to provide volume control for each track
        self.track_volumes = ParameterList(
            name="track_volumes",
            input_types=["float"],
            type="ParameterList",
            allowed_modes={ParameterMode.PROPERTY},
            default_value=[],
            tooltip="Volume levels for each audio track (0.0 = silent, 1.0 = full volume)",
            ui_options={"hide_property": False},
        )
        self.add_parameter(self.track_volumes)

        # Parameter to control how audio tracks are combined
        self.combine_mode = Parameter(
            name="combine_mode",
            type="str",
            allowed_modes={ParameterMode.PROPERTY},
            default_value="concatenate",
            tooltip="How to combine the audio tracks: 'concatenate' (one after another) or 'mix' (simultaneous playback)",
            traits={Options(choices=["concatenate", "mix"])},
        )
        self.add_parameter(self.combine_mode)

        # Parameter to control output format
        self.output_format = Parameter(
            name="output_format",
            type="str",
            allowed_modes={ParameterMode.PROPERTY},
            default_value="mp3",
            tooltip="Output audio format (mp3, wav, flac, etc.)",
            traits={Options(choices=["mp3", "wav", "flac", "aac", "ogg"])},
        )
        self.add_parameter(self.output_format)

        # Parameter to control audio quality/bitrate
        self.quality = Parameter(
            name="quality",
            type="str",
            allowed_modes={ParameterMode.PROPERTY},
            default_value="high",
            tooltip="Audio quality setting",
            traits={Options(choices=["low", "medium", "high", "lossless"])},
        )
        self.add_parameter(self.quality)

        # Output parameter for the combined audio file
        self.combined_audio = Parameter(
            name="combined_audio",
            type="AudioUrlArtifact",
            allowed_modes={ParameterMode.OUTPUT},
            default_value=None,
            tooltip="The combined audio file",
            ui_options={"pulse_on_run": True},
        )
        self.add_parameter(self.combined_audio)

        # Add status parameters for success/failure feedback
        # These provide detailed information about the audio combination process and results
        self._create_status_parameters(
            result_details_tooltip="Details about the audio combination result",
            result_details_placeholder="Details on the audio processing will be presented here.",
            parameter_group_initially_collapsed=False,
        )

        # Track the last audio list length to detect changes
        self._last_audio_list_length = 0

    def process(self) -> None:
        """Process the node by combining multiple audio tracks.

        This is the main execution method that:
        1. Resets the execution state and sets failure defaults
        2. Attempts to combine the input audio tracks using ffmpeg
        3. Handles any errors that occur during the combination process
        4. Sets success status with detailed result information

        The method follows the SuccessFailureNode pattern with comprehensive error handling
        and status reporting for a professional user experience.
        """
        # Reset execution state and set failure defaults
        self._clear_execution_status()
        self._set_failure_output_values()

        logger.debug(f"{self.name}: Called for node")

        # FAILURE CASES FIRST - Sync track volumes and attempt to combine audio tracks
        try:
            self._sync_track_volumes()
            self._combine_audio_tracks()
        except Exception as e:
            error_details = f"Failed to combine audio tracks: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.name}: {error_details}")
            self._handle_failure_exception(e)
            return

        # SUCCESS PATH AT END - Set success status with detailed information
        success_details = self._get_success_message()
        self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
        logger.debug(f"{self.name}: {success_details}")

    def _sync_track_volumes(self) -> None:
        """Sync track volumes with audio list length.

        This method ensures that the track_volumes ParameterList has the same length
        as the audio_list, adding default volume (1.0) for new tracks and removing
        excess volume controls when tracks are removed.
        """
        audio_list = self.get_parameter_value("audio_list")
        track_volumes = self.get_parameter_value("track_volumes")

        if not audio_list or not isinstance(audio_list, list):
            return

        audio_count = len(audio_list)

        # Ensure track_volumes is a list
        if not isinstance(track_volumes, list):
            track_volumes = []

        # Add default volumes for new tracks
        while len(track_volumes) < audio_count:
            track_volumes.append(1.0)  # Default to full volume

        # Remove excess volumes if audio list is shorter
        if len(track_volumes) > audio_count:
            track_volumes = track_volumes[:audio_count]

        # Update the parameter
        self.set_parameter_value("track_volumes", track_volumes)
        logger.debug(f"{self.name}: Synced {len(track_volumes)} volume controls with {audio_count} audio tracks")

    def _combine_audio_tracks(self) -> None:
        """Combine the input audio tracks into a single output file.

        This method implements the core audio combination logic:
        1. Downloads all input audio files to temporary files
        2. Uses ffmpeg to combine them based on the selected mode
        3. Uploads the result to static storage
        4. Sets the output parameter with the combined audio artifact
        """
        # Get and validate input parameters
        audio_list = self.get_parameter_value("audio_list")
        combine_mode = self.get_parameter_value("combine_mode")
        output_format = self.get_parameter_value("output_format")
        quality = self.get_parameter_value("quality")

        # FAILURE CASES FIRST - Validate inputs
        if not audio_list or not isinstance(audio_list, list) or len(audio_list) == 0:
            raise ValueError("Audio list is empty or invalid")

        MIN_AUDIO_FILES = 2
        if len(audio_list) < MIN_AUDIO_FILES:
            msg = "At least 2 audio files are required for combination"
            raise ValueError(msg)

        logger.debug(f"{self.name}: Processing {len(audio_list)} audio files with mode: {combine_mode}")

        # Download all audio files to temporary files
        temp_files = []
        try:
            for i, audio_item in enumerate(audio_list):
                if not isinstance(audio_item, AudioUrlArtifact):
                    msg = f"Audio item {i} is not an AudioUrlArtifact"
                    raise TypeError(msg)

                temp_file = self._download_audio_to_temp(audio_item, i)
                temp_files.append(temp_file)
                logger.debug(f"{self.name}: Downloaded audio {i + 1}/{len(audio_list)}")

            # Get track volumes
            track_volumes = self.get_parameter_value("track_volumes")
            if not isinstance(track_volumes, list):
                track_volumes = [1.0] * len(temp_files)

            # Ensure we have the right number of volumes
            while len(track_volumes) < len(temp_files):
                track_volumes.append(1.0)
            track_volumes = track_volumes[: len(temp_files)]

            # Combine audio files using ffmpeg
            combined_file = self._combine_with_ffmpeg(temp_files, track_volumes, combine_mode, output_format, quality)
            logger.debug(f"{self.name}: Successfully combined audio files")

            # Upload combined audio to static storage
            audio_artifact = self._upload_combined_audio(combined_file, output_format)
            self.parameter_output_values["combined_audio"] = audio_artifact

        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def _download_audio_to_temp(self, audio_artifact: AudioUrlArtifact, index: int) -> Path:
        """Download an audio file to a temporary file."""
        try:
            response = httpx.get(audio_artifact.value, timeout=60)
            response.raise_for_status()

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_file.write(response.content)
            temp_file.close()

            return Path(temp_file.name)
        except Exception as e:
            raise RuntimeError(f"Failed to download audio file {index + 1}: {e}") from e

    def _combine_with_ffmpeg(
        self, temp_files: list[Path], track_volumes: list[float], mode: str, format: str, quality: str
    ) -> Path:
        """Combine audio files using ffmpeg."""
        # Generate output filename
        output_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{format}")
        output_file.close()
        output_path = Path(output_file.name)

        try:
            if mode == "concatenate":
                self._concatenate_audio(temp_files, track_volumes, output_path, format, quality)
            elif mode == "mix":
                self._mix_audio(temp_files, track_volumes, output_path, format, quality)
            else:
                raise ValueError(f"Unknown combine mode: {mode}")

            return output_path
        except Exception as e:
            # Clean up output file on error
            try:
                output_path.unlink()
            except Exception:
                pass
            raise RuntimeError(f"Failed to combine audio with ffmpeg: {e}") from e

    def _concatenate_audio(
        self, temp_files: list[Path], track_volumes: list[float], output_path: Path, format: str, quality: str
    ) -> None:
        """Concatenate audio files one after another with volume control."""
        # For concatenation with volume control, we need to process each file individually
        # and then concatenate them. This is more complex but allows per-track volume control.

        # First, apply volume to each file and create temporary processed files
        processed_files = []
        try:
            for i, (temp_file, volume) in enumerate(zip(temp_files, track_volumes, strict=False)):
                if volume == 1.0:
                    # No volume adjustment needed
                    processed_files.append(temp_file)
                else:
                    # Apply volume adjustment
                    processed_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    processed_file.close()
                    processed_path = Path(processed_file.name)

                    # Apply volume using ffmpeg
                    volume_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(temp_file.absolute()),
                        "-af",
                        f"volume={volume}",
                        "-c:a",
                        "libmp3lame",
                        str(processed_path),
                    ]

                    result = subprocess.run(volume_cmd, check=False, capture_output=True, text=True, timeout=60)
                    if result.returncode != 0:
                        raise RuntimeError(f"ffmpeg volume adjustment failed: {result.stderr}")

                    processed_files.append(processed_path)

            # Now concatenate the processed files
            file_list = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
            for processed_file in processed_files:
                file_list.write(f"file '{processed_file.absolute()}'\n")
            file_list.close()
            file_list_path = Path(file_list.name)

            try:
                # Build ffmpeg command for concatenation
                cmd = [
                    "ffmpeg",
                    "-y",  # -y to overwrite output file
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(file_list_path),
                    "-c",
                    "copy" if format == "mp3" else "libmp3lame",
                ]

                # Add quality settings
                if quality == "high":
                    cmd.extend(["-b:a", "320k"])
                elif quality == "medium":
                    cmd.extend(["-b:a", "192k"])
                elif quality == "low":
                    cmd.extend(["-b:a", "128k"])

                cmd.append(str(output_path))

                # Run ffmpeg
                result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    raise RuntimeError(f"ffmpeg failed: {result.stderr}")

            finally:
                # Clean up file list
                try:
                    file_list_path.unlink()
                except Exception:
                    pass

        finally:
            # Clean up any temporary processed files we created
            for processed_file in processed_files:
                if processed_file != temp_files[processed_files.index(processed_file)]:
                    try:
                        processed_file.unlink()
                    except Exception:
                        pass

    def _mix_audio(
        self, temp_files: list[Path], track_volumes: list[float], output_path: Path, format: str, quality: str
    ) -> None:
        """Mix audio files to play simultaneously with volume control."""
        # Build ffmpeg command for mixing
        cmd = ["ffmpeg", "-y"]  # -y to overwrite output file

        # Add all input files
        for temp_file in temp_files:
            cmd.extend(["-i", str(temp_file.absolute())])

        # Build filter_complex with volume controls
        # Each input gets its volume applied, then they're mixed together
        filter_parts = []
        for i, volume in enumerate(track_volumes):
            if volume != 1.0:
                filter_parts.append(f"[{i}:a]volume={volume}[v{i}]")
            else:
                filter_parts.append(f"[{i}:a]copy[v{i}]")

        # Mix all the volume-adjusted tracks
        volume_inputs = "".join([f"[v{i}]" for i in range(len(temp_files))])
        filter_parts.append(f"{volume_inputs}amix=inputs={len(temp_files)}:duration=longest")

        filter_complex = ";".join(filter_parts)
        cmd.extend(["-filter_complex", filter_complex])

        # Add codec and quality settings
        if format == "mp3":
            cmd.extend(["-c:a", "libmp3lame"])
        elif format == "wav":
            cmd.extend(["-c:a", "pcm_s16le"])

        # Add quality settings
        if quality == "high":
            cmd.extend(["-b:a", "320k"])
        elif quality == "medium":
            cmd.extend(["-b:a", "192k"])
        elif quality == "low":
            cmd.extend(["-b:a", "128k"])

        cmd.append(str(output_path))

        # Run ffmpeg
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    def _upload_combined_audio(self, combined_file: Path, format: str) -> AudioUrlArtifact:
        """Upload the combined audio file to static storage."""
        # Read the combined audio file
        with open(combined_file, "rb") as f:
            audio_data = f.read()

        # Generate filename
        filename = generate_filename(
            node_name=self.name,
            suffix="_combined_audio",
            extension=format,
        )

        # Create upload URL request
        upload_request = CreateStaticFileUploadUrlRequest(file_name=filename)
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            raise RuntimeError(f"Failed to create upload URL: {upload_result.error}")

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            raise RuntimeError(f"Unexpected upload result type: {type(upload_result).__name__}")

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
            raise RuntimeError(f"Failed to upload combined audio: {e}") from e

        # Get download URL
        download_request = CreateStaticFileDownloadUrlRequest(file_name=filename)
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            raise RuntimeError(f"Failed to create download URL: {download_result.error}")

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            raise RuntimeError(f"Unexpected download result type: {type(download_result).__name__}")

        # Create and return AudioUrlArtifact
        return AudioUrlArtifact(value=download_result.url)

    def _get_success_message(self) -> str:
        """Generate success message with combination details."""
        try:
            audio_list = self.get_parameter_value("audio_list")
            combine_mode = self.get_parameter_value("combine_mode")
            track_volumes = self.get_parameter_value("track_volumes")
            if audio_list and isinstance(audio_list, list):
                track_count = len(audio_list)
                volume_info = ""
                if track_volumes and isinstance(track_volumes, list):
                    non_default_volumes = [v for v in track_volumes if v != 1.0]
                    if non_default_volumes:
                        volume_info = " with custom volume levels"
                return f"Successfully combined {track_count} audio tracks using {combine_mode} mode{volume_info}"
        except Exception as e:
            logger.warning(f"{self.name}: Error getting combination details: {e}")
        return "Successfully combined audio tracks"

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["combined_audio"] = None
