from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class AddFilmGrain(BaseVideoProcessor):
    """Add realistic film grain to video using sophisticated noise generation and luminance masking."""

    # Grain intensity constants
    MIN_GRAIN_INTENSITY = 0.05
    MAX_GRAIN_INTENSITY = 1.0
    DEFAULT_GRAIN_INTENSITY = 0.15

    # Luminance threshold constants
    MIN_LUMINANCE_THRESHOLD = 50
    MAX_LUMINANCE_THRESHOLD = 100
    DEFAULT_LUMINANCE_THRESHOLD = 75

    # Grain scale constants
    MIN_GRAIN_SCALE = 1.0
    MAX_GRAIN_SCALE = 4.0
    DEFAULT_GRAIN_SCALE = 2.0
    """Add realistic film grain to video using sophisticated noise generation and luminance masking."""

    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters for film grain."""
        # Add grain intensity parameter
        grain_intensity_parameter = Parameter(
            name="grain_intensity",
            type="float",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=self.DEFAULT_GRAIN_INTENSITY,
            tooltip=f"Film grain intensity ({self.MIN_GRAIN_INTENSITY} = subtle, {self.MAX_GRAIN_INTENSITY} = heavy grain)",
        )
        self.add_parameter(grain_intensity_parameter)
        grain_intensity_parameter.add_trait(Slider(min_val=self.MIN_GRAIN_INTENSITY, max_val=self.MAX_GRAIN_INTENSITY))

        # Add luminance threshold parameter
        luminance_threshold_parameter = Parameter(
            name="luminance_threshold",
            type="int",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=self.DEFAULT_LUMINANCE_THRESHOLD,
            tooltip=f"Luminance level where grain is most visible (typically {self.DEFAULT_LUMINANCE_THRESHOLD} for lighter areas)",
        )
        self.add_parameter(luminance_threshold_parameter)
        luminance_threshold_parameter.add_trait(
            Slider(min_val=self.MIN_LUMINANCE_THRESHOLD, max_val=self.MAX_LUMINANCE_THRESHOLD)
        )

        # Add grain scale parameter
        grain_scale_parameter = Parameter(
            name="grain_scale",
            type="float",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=self.DEFAULT_GRAIN_SCALE,
            tooltip="Grain scale factor (higher = larger grain particles)",
        )
        self.add_parameter(grain_scale_parameter)
        grain_scale_parameter.add_trait(Slider(min_val=self.MIN_GRAIN_SCALE, max_val=self.MAX_GRAIN_SCALE))

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "film grain addition"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build the FFmpeg command for film grain addition."""
        grain_intensity = kwargs.get("grain_intensity", self.DEFAULT_GRAIN_INTENSITY)
        luminance_threshold = kwargs.get("luminance_threshold", self.DEFAULT_LUMINANCE_THRESHOLD)
        grain_scale = kwargs.get("grain_scale", self.DEFAULT_GRAIN_SCALE)

        # Get FFmpeg paths and video properties
        ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()
        frame_rate, (width, height), duration = self._detect_video_properties(input_url, ffprobe_path)

        # Scale dimensions for grain generation (smaller = faster processing)
        scaled_width = int(width / grain_scale)
        scaled_height = int(height / grain_scale)

        # Log the detected framerate for debugging
        self.append_value_to_parameter("logs", f"Using detected framerate: {frame_rate} fps\n")

        # Build the complex filter for realistic film grain
        # Based on: https://gist.github.com/logiclrd/287140934c12bed1fd4be75e8624c118
        # The original uses two inputs and creates a sophisticated grain overlay

        # Use temporal grain (changes between frames) for realistic film grain effect
        random_expr = "random(1)*256"
        self.append_value_to_parameter("logs", "Temporal grain enabled: grain pattern changes between frames\n")

        # Build the complex filter for realistic film grain
        # Based on: https://gist.github.com/logiclrd/287140934c12bed1fd4be75e8624c118
        # The original uses two inputs and creates a sophisticated grain overlay

        # Use temporal grain (changes between frames) for realistic film grain effect
        random_expr = "random(1)*256"
        self.append_value_to_parameter("logs", "Temporal grain enabled: grain pattern changes between frames\n")

        custom_filter = f"""
        color=black:d={duration}:s={scaled_width}x{scaled_height}:r={frame_rate},
        geq=lum_expr={random_expr}:cb=128:cr=128,
        deflate=threshold0=15,
        dilation=threshold0=10,
        eq=contrast=3,
        scale={width}x{height} [n];
        [0] eq=saturation=0,geq=lum='{grain_intensity}*(182-abs({luminance_threshold}-lum(X,Y)))':cb=128:cr=128 [o];
        [n][o] blend=c0_mode=multiply,negate [a];
        color=c=black:d={duration}:s={width}x{height}:r={frame_rate} [b];
        [1][a] alphamerge [c];
        [b][c] overlay
        """.replace("\n", "").replace(" ", "")

        # Add frame rate filter if needed (after the grain effect)
        frame_rate_filter = self._get_frame_rate_filter(input_frame_rate)
        if frame_rate_filter:
            custom_filter = f"{custom_filter},{frame_rate_filter}"

        filter_complex = custom_filter

        # Get processing speed settings
        preset, pix_fmt, crf = self._get_processing_speed_settings()

        # Build FFmpeg command with processing speed settings
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_url,
            "-i",
            input_url,  # Second input as per the original gist
            "-filter_complex",
            filter_complex,
            "-c:a",
            "copy",
            "-c:v",
            "libx264",
            "-tune",
            "grain",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            pix_fmt,
            "-movflags",
            "+faststart",
            output_path,
        ]

        return cmd

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate custom parameters."""
        exceptions = []

        # Validate grain intensity
        grain_intensity = self.parameter_values.get("grain_intensity", self.DEFAULT_GRAIN_INTENSITY)
        if grain_intensity < self.MIN_GRAIN_INTENSITY or grain_intensity > self.MAX_GRAIN_INTENSITY:
            msg = f"{self.name}: Grain intensity must be between {self.MIN_GRAIN_INTENSITY} and {self.MAX_GRAIN_INTENSITY}"
            exceptions.append(ValueError(msg))

        # Validate luminance threshold
        luminance_threshold = self.parameter_values.get("luminance_threshold", self.DEFAULT_LUMINANCE_THRESHOLD)
        if luminance_threshold < self.MIN_LUMINANCE_THRESHOLD or luminance_threshold > self.MAX_LUMINANCE_THRESHOLD:
            msg = f"{self.name}: Luminance threshold must be between {self.MIN_LUMINANCE_THRESHOLD} and {self.MAX_LUMINANCE_THRESHOLD}"
            exceptions.append(ValueError(msg))

        # Validate grain scale
        grain_scale = self.parameter_values.get("grain_scale", self.DEFAULT_GRAIN_SCALE)
        if grain_scale < self.MIN_GRAIN_SCALE or grain_scale > self.MAX_GRAIN_SCALE:
            msg = f"{self.name}: Grain scale must be between {self.MIN_GRAIN_SCALE} and {self.MAX_GRAIN_SCALE}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing."""
        return {
            "grain_intensity": self.parameter_values.get("grain_intensity", self.DEFAULT_GRAIN_INTENSITY),
            "luminance_threshold": self.parameter_values.get("luminance_threshold", self.DEFAULT_LUMINANCE_THRESHOLD),
            "grain_scale": self.parameter_values.get("grain_scale", self.DEFAULT_GRAIN_SCALE),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get the output filename suffix."""
        grain_intensity = kwargs.get("grain_intensity", self.DEFAULT_GRAIN_INTENSITY)
        return f"_grain_{grain_intensity:.2f}"
