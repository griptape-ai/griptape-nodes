from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.traits.options import Options
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class FlipVideo(BaseVideoProcessor):
    """Flip video horizontally or vertically."""

    def _setup_custom_parameters(self) -> None:
        """Setup flip-specific parameters."""
        with ParameterGroup(name="flip_settings", ui_options={"collapsed": False}) as flip_group:
            # Flip direction parameter
            direction_parameter = Parameter(
                name="direction",
                type="str",
                default_value="horizontal",
                tooltip="Flip direction: horizontal or vertical",
            )
            self.add_parameter(direction_parameter)
            direction_parameter.add_trait(Options(choices=["horizontal", "vertical", "both"]))

        self.add_node_element(flip_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "video flipping"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build FFmpeg command for video flipping."""
        direction = kwargs.get("direction", "horizontal")

        # Determine flip filter based on direction
        if direction == "horizontal":
            custom_filter = "hflip"
        elif direction == "vertical":
            custom_filter = "vflip"
        else:  # "both"
            custom_filter = "hflip,vflip"

        # Combine with frame rate filter if needed
        filter_complex = self._combine_video_filters(custom_filter, input_frame_rate)

        # Get processing speed settings
        preset, pix_fmt, crf = self._get_processing_speed_settings()

        # Get ffmpeg executable path
        ffmpeg_path, _ = self._get_ffmpeg_paths()

        return [
            ffmpeg_path,
            "-i",
            input_url,
            "-vf",
            filter_complex,
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
            "copy",
            "-y",
            output_path,
        ]

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate flip parameters."""
        exceptions = []

        direction = self.get_parameter_value("direction")
        valid_choices = ["horizontal", "vertical", "both"]
        if direction is not None and direction not in valid_choices:
            msg = f"{self.name} - Direction must be one of {valid_choices}, got {direction}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, str]:
        """Get flip parameters."""
        return {
            "direction": self.get_parameter_value("direction"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        direction = kwargs.get("direction", "horizontal")
        return f"_flipped_{direction}"
