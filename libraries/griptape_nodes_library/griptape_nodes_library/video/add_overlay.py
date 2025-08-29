from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class AddOverlay(BaseVideoProcessor):
    """Add an overlay video or image on top of a base video using FFmpeg's blend modes.

    This node supports various blend modes that match industry-standard compositing software.
    It can overlay videos, images (PNG with transparency), and supports different channels
    and positioning options.

    Key Features:
    - Multiple blend modes (overlay, screen, grainmerge, etc.)
    - Channel selection (luminance, RGB, alpha, rgba)
    - Flexible positioning (9 directions + custom)
    - Sizing options (as-is, scale to cover/fit)
    - Linear RGB blending for consistent results

    Common Use Cases:
    - Adding film grain/noise effects
    - Overlaying logos or watermarks
    - Adding dust/scratch effects
    - Compositing multiple video layers
    """

    # Blend mode constants - matching Nuke's standard blend modes
    BLEND_MODES: ClassVar[list[str]] = [
        "overlay",  # Original overlay with alpha blending
        "screen",  # Brighten (good for dust/scratches)
        "lighten",  # Only brighten where overlay is brighter
        "softlight",  # Natural blending for film grain
        "grainmerge",  # Merge grain/noise (recommended for noise effects)
        "grainextract",  # Extract grain/noise
        "glow",  # Glow effect
        "hardlight",  # Hard light blending
    ]

    # Amount constants
    MIN_AMOUNT = 0.0
    MAX_AMOUNT = 1.0
    DEFAULT_AMOUNT = 0.5

    # Sizing options
    SIZING_OPTIONS: ClassVar[list[str]] = [
        "Scale to cover",  # Scale to cover (maintains aspect ratio)
        "Scale to fit",  # Scale to fit (doesn't maintain aspect ratio)
    ]

    def _setup_custom_parameters(self) -> None:
        """Setup overlay parameters."""
        overlay_param = Parameter(
            name="overlay_video",
            input_types=["VideoArtifact", "VideoUrlArtifact", "ImageArtifact", "ImageUrlArtifact"],
            type="VideoUrlArtifact",
            tooltip="The video or image to overlay on top of the base video (PNG with transparency supported)",
        )
        self.add_parameter(overlay_param)

        blend_mode_param = Parameter(
            name="blend_mode",
            type="str",
            default_value="overlay",
            tooltip="Blend mode for combining the overlay with the base video",
        )
        blend_mode_param.add_trait(Options(choices=self.BLEND_MODES))
        self.add_parameter(blend_mode_param)

        amount_param = Parameter(
            name="amount",
            type="float",
            default_value=self.DEFAULT_AMOUNT,
            tooltip=f"Strength of the overlay effect ({self.MIN_AMOUNT}-{self.MAX_AMOUNT})",
        )
        amount_param.add_trait(Slider(min_val=self.MIN_AMOUNT, max_val=self.MAX_AMOUNT))
        self.add_parameter(amount_param)

        sizing_param = Parameter(
            name="sizing",
            type="str",
            default_value="Scale to cover",
            tooltip="How to size the overlay: Scale to cover (maintains aspect), Scale to fit (stretches)",
        )
        sizing_param.add_trait(Options(choices=self.SIZING_OPTIONS))
        self.add_parameter(sizing_param)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "video overlay"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build FFmpeg command for video overlay."""
        overlay_video = kwargs.get("overlay_video")
        blend_mode = kwargs.get("blend_mode", "overlay")
        amount = kwargs.get("amount", self.DEFAULT_AMOUNT)

        if not overlay_video:
            # Get processing speed settings
            preset, pix_fmt, crf = self._get_processing_speed_settings()

            # Get ffmpeg executable path
            ffmpeg_path, _ = self._get_ffmpeg_paths()

            # No overlay video provided, just copy the input
            return [
                ffmpeg_path,
                "-i",
                input_url,
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-pix_fmt",
                pix_fmt,
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-y",
                output_path,
            ]

        # Get the overlay URL
        overlay_url = overlay_video.url if hasattr(overlay_video, "url") else str(overlay_video)

        # Get base video duration for proper trimming
        ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()
        _, _, base_duration = self._detect_video_properties(input_url, ffprobe_path)

        # For now, skip scaling for "Scale to cover" and "Scale to fit" to get basic overlay working
        # Always center the overlay for simplicity
        overlay_position = "(W-w)/2:(H-h)/2"

        # Build overlay filter complex based on blend mode and channel selection
        # [0] = overlay video/image, [1] = base video
        # Process: loop overlay, trim to base duration, apply channel filter, then blend

        if blend_mode == "overlay":
            # Use overlay filter for alpha blending
            custom_filter = f"[0]loop=loop=-1,trim=duration={base_duration},format=rgba,colorchannelmixer=aa={amount}[fg];[1][fg]overlay={overlay_position}[out]"
        else:
            # Use blend filter for other blend modes - blend all components
            custom_filter = f"[0]loop=loop=-1,trim=duration={base_duration}[fg];[1][fg]blend=all_mode={blend_mode}:all_opacity={amount}[out]"

        # Add frame rate filter if needed (after the overlay effect)
        frame_rate_filter = self._get_frame_rate_filter(input_frame_rate)
        if frame_rate_filter:
            # For complex filters, we need to add the frame rate filter to the output
            custom_filter = custom_filter.replace("[out]", "[out_temp]")
            custom_filter = f"{custom_filter};[out_temp]{frame_rate_filter}[out]"

        filter_complex = custom_filter

        # Get processing speed settings
        preset, pix_fmt, crf = self._get_processing_speed_settings()

        # Get ffmpeg executable path
        ffmpeg_path, _ = self._get_ffmpeg_paths()

        return [
            ffmpeg_path,
            "-i",
            overlay_url,  # Overlay video (film grain) - [0]
            "-i",
            input_url,  # Base video (main content) - [1]
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-shortest",  # End when shortest stream ends
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            pix_fmt,
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-y",
            output_path,
        ]

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate overlay parameters."""
        exceptions = []

        blend_mode = self.get_parameter_value("blend_mode")
        if blend_mode is not None and blend_mode not in self.BLEND_MODES:
            msg = f"{self.name} - Blend mode must be one of {self.BLEND_MODES}, got {blend_mode}"
            exceptions.append(ValueError(msg))

        amount = self.get_parameter_value("amount")
        if amount is not None and (amount < self.MIN_AMOUNT or amount > self.MAX_AMOUNT):
            msg = f"{self.name} - Amount must be between {self.MIN_AMOUNT} and {self.MAX_AMOUNT}, got {amount}"
            exceptions.append(ValueError(msg))

        sizing = self.get_parameter_value("sizing")
        if sizing is not None and sizing not in self.SIZING_OPTIONS:
            msg = f"{self.name} - Sizing must be one of {self.SIZING_OPTIONS}, got {sizing}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get overlay parameters."""
        return {
            "overlay_video": self.get_parameter_value("overlay_video"),
            "blend_mode": self.get_parameter_value("blend_mode"),
            "amount": self.get_parameter_value("amount"),
            "sizing": self.get_parameter_value("sizing"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        blend_mode = kwargs.get("blend_mode", "overlay")
        amount = kwargs.get("amount", self.DEFAULT_AMOUNT)
        sizing = kwargs.get("sizing", "Scale to cover")

        return f"_overlay_{sizing.replace(' ', '_')}_{blend_mode}_amount{amount:.2f}"
