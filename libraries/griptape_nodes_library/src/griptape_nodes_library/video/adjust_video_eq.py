from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class AdjustVideoEQ(BaseVideoProcessor):
    """Adjust video brightness, contrast, saturation, and gamma."""

    # Brightness constants
    MIN_BRIGHTNESS = -1.0
    MAX_BRIGHTNESS = 1.0
    DEFAULT_BRIGHTNESS = 0.0

    # Contrast constants
    MIN_CONTRAST = 0.0
    MAX_CONTRAST = 3.0
    DEFAULT_CONTRAST = 1.0

    # Saturation constants
    MIN_SATURATION = 0.0
    MAX_SATURATION = 3.0
    DEFAULT_SATURATION = 1.0

    # Gamma constants
    MIN_GAMMA = 0.1
    MAX_GAMMA = 10.0
    DEFAULT_GAMMA = 1.0

    def _setup_custom_parameters(self) -> None:
        """Setup EQ-specific parameters."""
        with ParameterGroup(name="eq_settings", ui_options={"collapsed": False}) as eq_group:
            # Brightness parameter
            brightness_parameter = Parameter(
                name="brightness",
                type="float",
                default_value=self.DEFAULT_BRIGHTNESS,
                tooltip=f"Brightness adjustment ({self.MIN_BRIGHTNESS}-{self.MAX_BRIGHTNESS})",
            )
            self.add_parameter(brightness_parameter)
            brightness_parameter.add_trait(Slider(min_val=self.MIN_BRIGHTNESS, max_val=self.MAX_BRIGHTNESS))

            # Contrast parameter
            contrast_parameter = Parameter(
                name="contrast",
                type="float",
                default_value=self.DEFAULT_CONTRAST,
                tooltip=f"Contrast adjustment ({self.MIN_CONTRAST}-{self.MAX_CONTRAST})",
            )
            self.add_parameter(contrast_parameter)
            contrast_parameter.add_trait(Slider(min_val=self.MIN_CONTRAST, max_val=self.MAX_CONTRAST))

            # Saturation parameter
            saturation_parameter = Parameter(
                name="saturation",
                type="float",
                default_value=self.DEFAULT_SATURATION,
                tooltip=f"Saturation adjustment ({self.MIN_SATURATION}-{self.MAX_SATURATION})",
            )
            self.add_parameter(saturation_parameter)
            saturation_parameter.add_trait(Slider(min_val=self.MIN_SATURATION, max_val=self.MAX_SATURATION))

            # Gamma parameter
            gamma_parameter = Parameter(
                name="gamma",
                type="float",
                default_value=self.DEFAULT_GAMMA,
                tooltip=f"Gamma adjustment ({self.MIN_GAMMA}-{self.MAX_GAMMA})",
            )
            self.add_parameter(gamma_parameter)
            gamma_parameter.add_trait(Slider(min_val=self.MIN_GAMMA, max_val=self.MAX_GAMMA))

        self.add_node_element(eq_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "video EQ adjustment"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build FFmpeg command for video EQ adjustment."""
        brightness = kwargs.get("brightness", self.DEFAULT_BRIGHTNESS)
        contrast = kwargs.get("contrast", self.DEFAULT_CONTRAST)
        saturation = kwargs.get("saturation", self.DEFAULT_SATURATION)
        gamma = kwargs.get("gamma", self.DEFAULT_GAMMA)

        # EQ filter: brightness, contrast, saturation, gamma
        custom_filter = f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}:gamma={gamma}"

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
        """Validate EQ parameters."""
        exceptions = []

        brightness = self.get_parameter_value("brightness")
        if brightness is not None and (brightness < self.MIN_BRIGHTNESS or brightness > self.MAX_BRIGHTNESS):
            msg = f"{self.name} - Brightness must be between {self.MIN_BRIGHTNESS} and {self.MAX_BRIGHTNESS}, got {brightness}"
            exceptions.append(ValueError(msg))

        contrast = self.get_parameter_value("contrast")
        if contrast is not None and (contrast < self.MIN_CONTRAST or contrast > self.MAX_CONTRAST):
            msg = f"{self.name} - Contrast must be between {self.MIN_CONTRAST} and {self.MAX_CONTRAST}, got {contrast}"
            exceptions.append(ValueError(msg))

        saturation = self.get_parameter_value("saturation")
        if saturation is not None and (saturation < self.MIN_SATURATION or saturation > self.MAX_SATURATION):
            msg = f"{self.name} - Saturation must be between {self.MIN_SATURATION} and {self.MAX_SATURATION}, got {saturation}"
            exceptions.append(ValueError(msg))

        gamma = self.get_parameter_value("gamma")
        if gamma is not None and (gamma < self.MIN_GAMMA or gamma > self.MAX_GAMMA):
            msg = f"{self.name} - Gamma must be between {self.MIN_GAMMA} and {self.MAX_GAMMA}, got {gamma}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get EQ parameters."""
        return {
            "brightness": self.get_parameter_value("brightness"),
            "contrast": self.get_parameter_value("contrast"),
            "saturation": self.get_parameter_value("saturation"),
            "gamma": self.get_parameter_value("gamma"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        brightness = kwargs.get("brightness", self.DEFAULT_BRIGHTNESS)
        contrast = kwargs.get("contrast", self.DEFAULT_CONTRAST)
        saturation = kwargs.get("saturation", self.DEFAULT_SATURATION)
        gamma = kwargs.get("gamma", self.DEFAULT_GAMMA)
        return f"_eq_b{brightness:.2f}_c{contrast:.2f}_s{saturation:.2f}_g{gamma:.2f}"
