"""Video artifact provider."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_provider import (
    BaseArtifactMetadata,
    BaseArtifactProvider,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_preview_generator import (
        BaseArtifactPreviewGenerator,
    )
    from griptape_nodes.retained_mode.managers.artifact_providers.provider_registry import ProviderRegistry

logger = logging.getLogger("griptape_nodes")


class VideoArtifactMetadata(BaseArtifactMetadata):
    """Metadata extracted from a video source file via ffprobe."""

    width: int
    height: int
    duration_seconds: float
    codec: str
    frame_rate: float
    file_size: int


class VideoArtifactProvider(BaseArtifactProvider):
    """Provider for video artifacts.

    Uses ffmpeg/ffprobe for metadata extraction and preview generation.
    ffmpeg must be available on the system PATH.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        """Initialize the video artifact provider.

        Args:
            registry: The ProviderRegistry that manages this provider
        """
        super().__init__(registry)

    @classmethod
    def get_friendly_name(cls) -> str:
        return "Video"

    @classmethod
    def get_supported_formats(cls) -> set[str]:
        return {"mov", "mp4", "avi", "mkv", "webm", "m4v", "flv", "wmv"}

    @classmethod
    def get_preview_formats(cls) -> set[str]:
        return {"mp4"}

    @classmethod
    def get_default_preview_generator(cls) -> str:
        return "Standard Video Preview Generation"

    @classmethod
    def get_default_preview_format(cls) -> str:
        return "mp4"

    @classmethod
    def get_default_preview_generators(cls) -> list[type[BaseArtifactPreviewGenerator]]:
        """Get default preview generator classes."""
        from griptape_nodes.retained_mode.managers.artifact_providers.video.preview_generators import (
            FFmpegPreviewGenerator,
        )

        return [FFmpegPreviewGenerator]

    @classmethod
    def get_artifact_metadata(cls, source_path: str) -> VideoArtifactMetadata | None:
        """Extract video metadata via ffprobe."""
        if shutil.which("ffprobe") is None:
            logger.warning("ffprobe not found on system PATH")
            return None

        try:
            result = subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "ffprobe",
                    # Suppress all log output
                    "-v",
                    "quiet",
                    # Output as JSON for easy parsing
                    "-print_format",
                    "json",
                    # Include per-stream info (codec, dimensions, frame rate, etc.)
                    "-show_streams",
                    # Include container-level info (duration, size, etc.)
                    "-show_format",
                    source_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            if result.returncode != 0:
                return None

            probe_data = json.loads(result.stdout)

            # Find the first video stream
            video_stream = None
            for stream in probe_data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if video_stream is None:
                return None

            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            codec = video_stream.get("codec_name", "unknown")

            # Parse frame rate from r_frame_rate (e.g., "30/1" or "24000/1001")
            frame_rate = 0.0
            r_frame_rate = video_stream.get("r_frame_rate", "0/1")
            if "/" in r_frame_rate:
                num, den = r_frame_rate.split("/")
                if int(den) != 0:
                    frame_rate = int(num) / int(den)

            # Duration from stream or format level
            duration_seconds = float(video_stream.get("duration", 0.0))
            if duration_seconds == 0.0:
                format_info = probe_data.get("format", {})
                duration_seconds = float(format_info.get("duration", 0.0))

            file_size = Path(source_path).stat().st_size

            return VideoArtifactMetadata(
                width=width,
                height=height,
                duration_seconds=duration_seconds,
                codec=codec,
                frame_rate=round(frame_rate, 3),
                file_size=file_size,
            )
        except Exception:
            return None
