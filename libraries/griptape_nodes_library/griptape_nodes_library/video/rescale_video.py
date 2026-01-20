from dataclasses import dataclass
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


@dataclass(frozen=True)
class ScaleSettings:
    resize_mode: str
    target_size: int
    percentage_scale: int
    target_width: int
    target_height: int
    fit_mode: str
    background_color: str
    resample_filter: str


class RescaleVideo(BaseVideoProcessor):
    """Rescale a video with different resize modes and resample filters."""

    RESIZE_MODE_WIDTH = "width"
    RESIZE_MODE_HEIGHT = "height"
    RESIZE_MODE_PERCENTAGE = "percentage"
    RESIZE_MODE_WIDTH_HEIGHT = "width and height"

    MIN_TARGET_SIZE = 1
    MAX_TARGET_SIZE = 8000
    DEFAULT_TARGET_SIZE = 1000
    MIN_EVEN_DIMENSION = 2

    MIN_PERCENTAGE_SCALE = 1
    MAX_PERCENTAGE_SCALE = 500
    DEFAULT_PERCENTAGE_SCALE = 100

    FIT_MODE_FIT = "fit"
    FIT_MODE_FILL = "fill"
    FIT_MODE_STRETCH = "stretch"

    HEX_SHORT_LENGTH = 3
    HEX_FULL_LENGTH = 6

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "resize_mode":
            if value == self.RESIZE_MODE_PERCENTAGE:
                self.show_parameter_by_name("percentage_scale")
                self.hide_parameter_by_name("target_size")
                self.hide_parameter_by_name("target_width")
                self.hide_parameter_by_name("target_height")
                self.hide_parameter_by_name("fit_mode")
                self.hide_parameter_by_name("background_color")
            elif value == self.RESIZE_MODE_WIDTH_HEIGHT:
                self.hide_parameter_by_name("percentage_scale")
                self.hide_parameter_by_name("target_size")
                self.show_parameter_by_name("target_width")
                self.show_parameter_by_name("target_height")
                self.show_parameter_by_name("fit_mode")
                self.hide_parameter_by_name("background_color")
            else:
                self.hide_parameter_by_name("percentage_scale")
                self.show_parameter_by_name("target_size")
                self.hide_parameter_by_name("target_width")
                self.hide_parameter_by_name("target_height")
                self.hide_parameter_by_name("fit_mode")
                self.hide_parameter_by_name("background_color")
        elif parameter.name == "fit_mode":
            if value == self.FIT_MODE_FIT:
                self.show_parameter_by_name("background_color")
            else:
                self.hide_parameter_by_name("background_color")
        return super().after_value_set(parameter, value)

    def _setup_custom_parameters(self) -> None:
        with ParameterGroup(name="rescale_settings", ui_options={"collapsed": False}) as rescale_group:
            resize_mode_param = Parameter(
                name="resize_mode",
                type="str",
                default_value=self.RESIZE_MODE_PERCENTAGE,
                tooltip="How to resize the video: by width, height, percentage, or width and height",
            )
            resize_mode_param.add_trait(
                Options(
                    choices=[
                        self.RESIZE_MODE_WIDTH,
                        self.RESIZE_MODE_HEIGHT,
                        self.RESIZE_MODE_WIDTH_HEIGHT,
                        self.RESIZE_MODE_PERCENTAGE,
                    ]
                )
            )

            target_size_param = Parameter(
                name="target_size",
                type="int",
                default_value=self.DEFAULT_TARGET_SIZE,
                tooltip=f"Target size in pixels for width/height modes ({self.MIN_TARGET_SIZE}-{self.MAX_TARGET_SIZE})",
            )
            target_size_param.add_trait(Slider(min_val=self.MIN_TARGET_SIZE, max_val=self.MAX_TARGET_SIZE))

            percentage_scale_param = Parameter(
                name="percentage_scale",
                input_types=["int", "float"],
                type="int",
                default_value=self.DEFAULT_PERCENTAGE_SCALE,
                tooltip=f"Scale factor as percentage ({self.MIN_PERCENTAGE_SCALE}-{self.MAX_PERCENTAGE_SCALE}%, 100% = original size)",
            )
            percentage_scale_param.add_trait(
                Slider(min_val=self.MIN_PERCENTAGE_SCALE, max_val=self.MAX_PERCENTAGE_SCALE)
            )

            target_width_param = ParameterInt(
                name="target_width",
                max_val=self.MAX_TARGET_SIZE,
                default_value=self.DEFAULT_TARGET_SIZE,
                tooltip=f"Target width in pixels ({self.MIN_TARGET_SIZE}-{self.MAX_TARGET_SIZE})",
            )
            target_width_param.add_trait(Slider(min_val=self.MIN_TARGET_SIZE, max_val=self.MAX_TARGET_SIZE))

            target_height_param = ParameterInt(
                name="target_height",
                max_val=self.MAX_TARGET_SIZE,
                default_value=self.DEFAULT_TARGET_SIZE,
                tooltip=f"Target height in pixels ({self.MIN_TARGET_SIZE}-{self.MAX_TARGET_SIZE})",
            )
            target_height_param.add_trait(Slider(min_val=self.MIN_TARGET_SIZE, max_val=self.MAX_TARGET_SIZE))

            fit_mode_param = Parameter(
                name="fit_mode",
                type="str",
                default_value=self.FIT_MODE_FIT,
                tooltip="How to fit the video within the target dimensions",
            )
            fit_mode_param.add_trait(
                Options(
                    choices=[
                        self.FIT_MODE_FIT,
                        self.FIT_MODE_FILL,
                        self.FIT_MODE_STRETCH,
                    ]
                )
            )

            background_color_param = Parameter(
                name="background_color",
                type="str",
                default_value="#000000",
                tooltip="Background color for letterboxing/matting",
            )
            background_color_param.add_trait(ColorPicker(format="hex"))

            resample_filter_param = Parameter(
                name="resample_filter",
                type="str",
                default_value="lanczos",
                tooltip="Resample filter for resizing (higher quality = slower processing)",
            )
            resample_filter_param.add_trait(Options(choices=["neighbor", "bilinear", "bicubic", "lanczos"]))

        self.add_node_element(rescale_group)

        self.hide_parameter_by_name("target_size")
        self.hide_parameter_by_name("target_width")
        self.hide_parameter_by_name("target_height")
        self.hide_parameter_by_name("fit_mode")
        self.hide_parameter_by_name("background_color")

    def _get_processing_description(self) -> str:
        return "video rescaling"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()

        resize_mode = kwargs.get("resize_mode", self.RESIZE_MODE_PERCENTAGE)
        target_size = int(kwargs.get("target_size", self.DEFAULT_TARGET_SIZE))
        percentage_scale = int(kwargs.get("percentage_scale", self.DEFAULT_PERCENTAGE_SCALE))
        target_width = int(kwargs.get("target_width", self.DEFAULT_TARGET_SIZE))
        target_height = int(kwargs.get("target_height", self.DEFAULT_TARGET_SIZE))
        fit_mode = kwargs.get("fit_mode", self.FIT_MODE_FIT)
        background_color = kwargs.get("background_color", "#000000")
        resample_filter = kwargs.get("resample_filter", "lanczos")

        settings = ScaleSettings(
            resize_mode=resize_mode,
            target_size=target_size,
            percentage_scale=percentage_scale,
            target_width=target_width,
            target_height=target_height,
            fit_mode=fit_mode,
            background_color=background_color,
            resample_filter=resample_filter,
        )

        scale_filter = self._build_scale_filter(settings)

        video_filter = self._combine_video_filters(scale_filter, input_frame_rate)

        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_url,
            "-vf",
            video_filter,
        ]

        has_audio = self._detect_audio_stream(input_url, ffprobe_path)
        if has_audio:
            cmd.extend(["-c:a", "copy"])
        else:
            cmd.extend(["-an"])

        preset, pixel_format, crf = self._get_processing_speed_settings()
        cmd.extend(["-preset", preset, "-pix_fmt", pixel_format, "-crf", str(crf)])
        cmd.append(output_path)

        return cmd

    def _build_scale_filter(self, settings: ScaleSettings) -> str:
        if settings.resize_mode == self.RESIZE_MODE_WIDTH:
            even_width = self._make_even(settings.target_size)
            return f"scale={even_width}:-2:flags={settings.resample_filter}"

        if settings.resize_mode == self.RESIZE_MODE_HEIGHT:
            even_height = self._make_even(settings.target_size)
            return f"scale=-2:{even_height}:flags={settings.resample_filter}"

        if settings.resize_mode == self.RESIZE_MODE_PERCENTAGE:
            scale_factor = settings.percentage_scale / 100.0
            return f"scale=trunc(iw*{scale_factor}/2)*2:trunc(ih*{scale_factor}/2)*2:flags={settings.resample_filter}"

        if settings.resize_mode == self.RESIZE_MODE_WIDTH_HEIGHT:
            even_width = self._make_even(settings.target_width)
            even_height = self._make_even(settings.target_height)

            if settings.fit_mode == self.FIT_MODE_STRETCH:
                return f"scale={even_width}:{even_height}:flags={settings.resample_filter}"

            if settings.fit_mode == self.FIT_MODE_FILL:
                return (
                    f"scale={even_width}:{even_height}:force_original_aspect_ratio=increase:"
                    f"flags={settings.resample_filter},crop={even_width}:{even_height}"
                )

            pad_color = self._format_ffmpeg_color(settings.background_color)
            return (
                f"scale={even_width}:{even_height}:force_original_aspect_ratio=decrease:"
                f"flags={settings.resample_filter},pad={even_width}:{even_height}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
            )

        error_msg = f"{self.name}: Invalid resize mode: {settings.resize_mode}"
        raise ValueError(error_msg)

    def _make_even(self, value: int) -> int:
        even_value = (max(1, value) // 2) * 2
        if even_value < self.MIN_EVEN_DIMENSION:
            return self.MIN_EVEN_DIMENSION
        return even_value

    def _format_ffmpeg_color(self, color_value: str) -> str:
        if not color_value:
            return "0xFFFFFF"

        cleaned = color_value.lstrip("#")
        if len(cleaned) == self.HEX_SHORT_LENGTH:
            cleaned = "".join([c * 2 for c in cleaned])
        if len(cleaned) != self.HEX_FULL_LENGTH:
            return "0xFFFFFF"
        return f"0x{cleaned}"

    def _validate_custom_parameters(self) -> list[Exception] | None:
        exceptions = []

        resize_mode = self.get_parameter_value("resize_mode")
        target_size = self.get_parameter_value("target_size")
        percentage_scale = self.get_parameter_value("percentage_scale")
        target_width = self.get_parameter_value("target_width")
        target_height = self.get_parameter_value("target_height")

        if (
            resize_mode in [self.RESIZE_MODE_WIDTH, self.RESIZE_MODE_HEIGHT]
            and target_size is not None
            and (target_size < self.MIN_TARGET_SIZE or target_size > self.MAX_TARGET_SIZE)
        ):
            msg = f"{self.name} - Target size must be between {self.MIN_TARGET_SIZE} and {self.MAX_TARGET_SIZE}, got {target_size}"
            exceptions.append(ValueError(msg))

        if (
            resize_mode == self.RESIZE_MODE_PERCENTAGE
            and percentage_scale is not None
            and (percentage_scale < self.MIN_PERCENTAGE_SCALE or percentage_scale > self.MAX_PERCENTAGE_SCALE)
        ):
            msg = f"{self.name} - Percentage scale must be between {self.MIN_PERCENTAGE_SCALE} and {self.MAX_PERCENTAGE_SCALE}, got {percentage_scale}"
            exceptions.append(ValueError(msg))

        if resize_mode == self.RESIZE_MODE_WIDTH_HEIGHT:
            if target_width is not None and (
                target_width < self.MIN_TARGET_SIZE or target_width > self.MAX_TARGET_SIZE
            ):
                msg = f"{self.name} - Target width must be between {self.MIN_TARGET_SIZE} and {self.MAX_TARGET_SIZE}, got {target_width}"
                exceptions.append(ValueError(msg))

            if target_height is not None and (
                target_height < self.MIN_TARGET_SIZE or target_height > self.MAX_TARGET_SIZE
            ):
                msg = f"{self.name} - Target height must be between {self.MIN_TARGET_SIZE} and {self.MAX_TARGET_SIZE}, got {target_height}"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        return {
            "resize_mode": self.get_parameter_value("resize_mode"),
            "target_size": self.get_parameter_value("target_size"),
            "percentage_scale": self.get_parameter_value("percentage_scale"),
            "target_width": self.get_parameter_value("target_width"),
            "target_height": self.get_parameter_value("target_height"),
            "fit_mode": self.get_parameter_value("fit_mode"),
            "background_color": self.get_parameter_value("background_color"),
            "resample_filter": self.get_parameter_value("resample_filter"),
        }

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        return "_rescaled"
