import random
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class AddRGBShift(BaseVideoProcessor):
    """Add RGB shift (chromatic aberration) effect to video."""

    # RGB shift constants
    MIN_SHIFT = -20
    MAX_SHIFT = 20
    DEFAULT_SHIFT = 6

    # RGB shift intensity constants
    MIN_INTENSITY = 0.0
    MAX_INTENSITY = 1.0
    DEFAULT_INTENSITY = 1.0

    # Animated glitch timing constants
    MIN_GLITCH_FREQUENCY = 0.1
    MAX_GLITCH_FREQUENCY = 10.0
    DEFAULT_GLITCH_FREQUENCY = 2.0

    MIN_GLITCH_INTENSITY = 0.0
    MAX_GLITCH_INTENSITY = 1.0
    DEFAULT_GLITCH_INTENSITY = 0.5

    MIN_GLITCH_DURATION = 0.01
    MAX_GLITCH_DURATION = 0.5
    DEFAULT_GLITCH_DURATION = 0.1

    # Visual effect constants
    MIN_NOISE_STRENGTH = 0
    MAX_NOISE_STRENGTH = 50
    DEFAULT_NOISE_STRENGTH = 8

    MIN_CHROMA_SHIFT = -10
    MAX_CHROMA_SHIFT = 10
    DEFAULT_CHROMA_SHIFT_H = 2
    DEFAULT_CHROMA_SHIFT_V = -2

    MIN_BLUR_STRENGTH = 0.0
    MAX_BLUR_STRENGTH = 3.0
    DEFAULT_BLUR_STRENGTH = 0.8

    MIN_MOTION_TRAILS = 1
    MAX_MOTION_TRAILS = 5
    DEFAULT_MOTION_TRAILS = 3

    # Glitch timing variation constants
    GLITCH_DURATION_VARIATION_MIN = 0.8
    GLITCH_DURATION_VARIATION_MAX = 1.2
    GLITCH_INTERVAL_VARIATION_MIN = 0.5
    GLITCH_INTERVAL_VARIATION_MAX = 2.0

    # Burst glitch timing constants
    BURST_GAP_MIN = 0.05
    BURST_GAP_MAX = 0.15

    # Tear position constants
    TEAR_POSITION_MIN = 0.1
    TEAR_POSITION_MAX = 0.9

    # Glitch burst constants
    GLITCH_BURST_PROBABILITY = 0.3
    GLITCH_BURST_COUNT_MIN = 2
    GLITCH_BURST_COUNT_MAX = 3

    # Glitch timing constants
    GLITCH_START_DELAY_MIN = 0.5
    GLITCH_START_DELAY_MAX = 2.0
    GLITCH_TIME_LIMIT = 10.0
    GLITCH_MIN_COUNT = 20

    # Tear effect constants
    MIN_TEAR_OFFSET = -50
    MAX_TEAR_OFFSET = 50
    DEFAULT_TEAR_OFFSET_MIN = 5
    DEFAULT_TEAR_OFFSET_MAX = 15

    def _setup_custom_parameters(self) -> None:
        """Setup RGB shift-specific parameters."""
        # Glitch mode (at the top level)
        glitch_mode_parameter = Parameter(
            name="glitch_mode",
            type="str",
            default_value="static",
            tooltip="Glitch animation: static (constant RGB shift) or animated (intermittent RGB shift with timing and tear effects)",
        )
        self.add_parameter(glitch_mode_parameter)
        glitch_mode_parameter.add_trait(Options(choices=["static", "animated"]))
        with ParameterGroup(name="glitched_visual_style", ui_options={"collapsed": False}) as glitched_group:
            # Red channel horizontal shift
            Parameter(
                name="red_horizontal",
                type="int",
                default_value=-self.DEFAULT_SHIFT,
                tooltip=f"Red channel horizontal shift during glitches ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Red channel vertical shift
            Parameter(
                name="red_vertical",
                type="int",
                default_value=0,
                tooltip=f"Red channel vertical shift during glitches ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Green channel horizontal shift
            Parameter(
                name="green_horizontal",
                type="int",
                default_value=self.DEFAULT_SHIFT,
                tooltip=f"Green channel horizontal shift during glitches ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Green channel vertical shift
            Parameter(
                name="green_vertical",
                type="int",
                default_value=0,
                tooltip=f"Green channel vertical shift during glitches ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Blue channel horizontal shift
            Parameter(
                name="blue_horizontal",
                type="int",
                default_value=0,
                tooltip=f"Blue channel horizontal shift during glitches ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Blue channel vertical shift
            Parameter(
                name="blue_vertical",
                type="int",
                default_value=0,
                tooltip=f"Blue channel vertical shift during glitches ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Overall intensity
            Parameter(
                name="intensity",
                type="float",
                default_value=self.DEFAULT_INTENSITY,
                tooltip=f"Overall intensity of the RGB shift effect during glitches ({self.MIN_INTENSITY}-{self.MAX_INTENSITY})",
            ).add_trait(Slider(min_val=self.MIN_INTENSITY, max_val=self.MAX_INTENSITY))

        self.add_node_element(glitched_group)

        # Glitch animation settings (timing and frequency)
        with ParameterGroup(name="glitch_animation_settings", ui_options={"collapsed": True}) as animation_group:
            Parameter(
                name="glitch_frequency",
                type="float",
                default_value=self.DEFAULT_GLITCH_FREQUENCY,
                tooltip=f"Number of glitches per second when animated ({self.MIN_GLITCH_FREQUENCY}-{self.MAX_GLITCH_FREQUENCY})",
            ).add_trait(Slider(min_val=self.MIN_GLITCH_FREQUENCY, max_val=self.MAX_GLITCH_FREQUENCY))

            Parameter(
                name="glitch_duration",
                type="float",
                default_value=self.DEFAULT_GLITCH_DURATION,
                tooltip=f"Duration of each glitch in seconds when animated ({self.MIN_GLITCH_DURATION}-{self.MAX_GLITCH_DURATION})",
            ).add_trait(Slider(min_val=self.MIN_GLITCH_DURATION, max_val=self.MAX_GLITCH_DURATION))

            Parameter(
                name="glitch_intensity",
                type="float",
                default_value=self.DEFAULT_GLITCH_INTENSITY,
                tooltip=f"Intensity of glitch shifts when animated ({self.MIN_GLITCH_INTENSITY}-{self.MAX_GLITCH_INTENSITY})",
            ).add_trait(Slider(min_val=self.MIN_GLITCH_INTENSITY, max_val=self.MAX_GLITCH_INTENSITY))

        self.add_node_element(animation_group)

        # Tear effects (randomly occur during animated glitches)
        with ParameterGroup(name="tear_effects", ui_options={"collapsed": True}) as tear_group:
            Parameter(
                name="tear_offset_min",
                type="int",
                default_value=self.DEFAULT_TEAR_OFFSET_MIN,
                tooltip=f"Minimum horizontal offset for tear effect - randomly occurs during glitches ({self.MIN_TEAR_OFFSET} to {self.MAX_TEAR_OFFSET} pixels)",
            ).add_trait(Slider(min_val=self.MIN_TEAR_OFFSET, max_val=self.MAX_TEAR_OFFSET))

            Parameter(
                name="tear_offset_max",
                type="int",
                default_value=self.DEFAULT_TEAR_OFFSET_MAX,
                tooltip=f"Maximum horizontal offset for tear effect - randomly occurs during glitches ({self.MIN_TEAR_OFFSET} to {self.MAX_TEAR_OFFSET} pixels)",
            ).add_trait(Slider(min_val=self.MIN_TEAR_OFFSET, max_val=self.MAX_TEAR_OFFSET))

        self.add_node_element(tear_group)

        # Random seed for glitch reproducibility
        with ParameterGroup(name="random_seed_settings", ui_options={"collapsed": True}) as seed_group:
            Parameter(
                name="random_seed",
                type="int",
                default_value=42,
                tooltip="Random seed for glitch timing. Use -1 for truly random patterns each time, or any positive number for reproducible patterns.",
            )

        self.add_node_element(seed_group)

        # Non-glitched visual style (VHS base effects)
        with ParameterGroup(name="non_glitched_visual_style", ui_options={"collapsed": True}) as vhs_group:
            Parameter(
                name="noise_strength",
                type="int",
                default_value=self.DEFAULT_NOISE_STRENGTH,
                tooltip=f"Tape noise strength - always active ({self.MIN_NOISE_STRENGTH}-{self.MAX_NOISE_STRENGTH})",
            ).add_trait(Slider(min_val=self.MIN_NOISE_STRENGTH, max_val=self.MAX_NOISE_STRENGTH))

            Parameter(
                name="chroma_shift_horizontal",
                type="int",
                default_value=self.DEFAULT_CHROMA_SHIFT_H,
                tooltip=f"Chroma shift horizontal - always active ({self.MIN_CHROMA_SHIFT}-{self.MAX_CHROMA_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_CHROMA_SHIFT, max_val=self.MAX_CHROMA_SHIFT))

            Parameter(
                name="chroma_shift_vertical",
                type="int",
                default_value=self.DEFAULT_CHROMA_SHIFT_V,
                tooltip=f"Chroma shift vertical - always active ({self.MIN_CHROMA_SHIFT}-{self.MAX_CHROMA_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_CHROMA_SHIFT, max_val=self.MAX_CHROMA_SHIFT))

            Parameter(
                name="blur_strength",
                type="float",
                default_value=self.DEFAULT_BLUR_STRENGTH,
                tooltip=f"Blur strength - always active ({self.MIN_BLUR_STRENGTH}-{self.MAX_BLUR_STRENGTH})",
            ).add_trait(Slider(min_val=self.MIN_BLUR_STRENGTH, max_val=self.MAX_BLUR_STRENGTH))

            Parameter(
                name="motion_trails",
                type="int",
                default_value=self.DEFAULT_MOTION_TRAILS,
                tooltip=f"Motion trail frames - always active ({self.MIN_MOTION_TRAILS}-{self.MAX_MOTION_TRAILS})",
            ).add_trait(Slider(min_val=self.MIN_MOTION_TRAILS, max_val=self.MAX_MOTION_TRAILS))

        self.add_node_element(vhs_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "RGB shift (chromatic aberration) addition"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, **kwargs) -> list[str]:  # noqa: PLR0915
        """Build FFmpeg command for RGB shift effect."""
        red_h = kwargs.get("red_horizontal", -self.DEFAULT_SHIFT)
        red_v = kwargs.get("red_vertical", 0)
        green_h = kwargs.get("green_horizontal", self.DEFAULT_SHIFT)
        green_v = kwargs.get("green_vertical", 0)
        blue_h = kwargs.get("blue_horizontal", 0)
        blue_v = kwargs.get("blue_vertical", 0)
        intensity = kwargs.get("intensity", self.DEFAULT_INTENSITY)

        # Animated glitch parameters
        glitch_mode = kwargs.get("glitch_mode", "static")
        glitch_freq = kwargs.get("glitch_frequency", self.DEFAULT_GLITCH_FREQUENCY)
        glitch_duration = kwargs.get("glitch_duration", self.DEFAULT_GLITCH_DURATION)

        # Visual effect parameters
        noise_strength = kwargs.get("noise_strength", self.DEFAULT_NOISE_STRENGTH)
        chroma_shift_h = kwargs.get("chroma_shift_horizontal", self.DEFAULT_CHROMA_SHIFT_H)
        chroma_shift_v = kwargs.get("chroma_shift_vertical", self.DEFAULT_CHROMA_SHIFT_V)
        blur_strength = kwargs.get("blur_strength", self.DEFAULT_BLUR_STRENGTH)
        motion_trails = kwargs.get("motion_trails", self.DEFAULT_MOTION_TRAILS)

        # Tear effect parameters
        tear_offset_min = kwargs.get("tear_offset_min", self.DEFAULT_TEAR_OFFSET_MIN)
        tear_offset_max = kwargs.get("tear_offset_max", self.DEFAULT_TEAR_OFFSET_MAX)

        if glitch_mode == "animated":
            # Animated glitch with multiple effects
            # Calculate base shift amounts
            red_h_scaled = int(red_h * intensity)
            red_v_scaled = int(red_v * intensity)
            green_h_scaled = int(green_h * intensity)
            green_v_scaled = int(green_v * intensity)
            blue_h_scaled = int(blue_h * intensity)
            blue_v_scaled = int(blue_v * intensity)

            # Create timeline enable expression for periodic glitches
            # Stack multiple between() functions to create glitches throughout the video

            # Create realistic VHS glitch pattern with random timing
            # This creates sporadic, unpredictable glitches instead of regular pulses

            # Set seed for reproducible but random glitches
            random_seed = kwargs.get("random_seed", 42)
            if random_seed >= 0:
                random.seed(random_seed)  # Fixed seed for consistent results

            # Calculate base timing
            avg_interval = 1.0 / glitch_freq  # Average time between glitches

            # Create glitches with random timing and varying durations
            enable_expr = ""
            # Start with a delay to avoid glitches at the very beginning
            current_time = random.uniform(  # noqa: S311
                self.GLITCH_START_DELAY_MIN, self.GLITCH_START_DELAY_MAX
            )  # Random delay between 0.5-2 seconds
            glitch_count = 0
            max_glitches = max(self.GLITCH_MIN_COUNT, int(glitch_freq * 15))  # More glitches for better coverage

            while current_time < self.GLITCH_TIME_LIMIT and glitch_count < max_glitches:  # Cover first 10 seconds
                # Random interval with some clustering (glitches sometimes come in bursts)
                if random.uniform(0, 1) < self.GLITCH_BURST_PROBABILITY:  # 30% chance of glitch burst  # noqa: S311
                    # Create 2-3 glitches in quick succession
                    burst_count = random.randint(self.GLITCH_BURST_COUNT_MIN, self.GLITCH_BURST_COUNT_MAX)  # noqa: S311
                    for _ in range(burst_count):
                        if glitch_count > 0:
                            enable_expr += "+"

                            # Vary the duration slightly for more realism
                    actual_duration = glitch_duration * random.uniform(  # noqa: S311
                        self.GLITCH_DURATION_VARIATION_MIN, self.GLITCH_DURATION_VARIATION_MAX
                    )
                    enable_expr += f"between(t,{current_time},{current_time + actual_duration})"

                    current_time += random.uniform(  # noqa: S311
                        self.BURST_GAP_MIN, self.BURST_GAP_MAX
                    )  # Short gaps between burst glitches
                    glitch_count += 1

                    if current_time >= self.GLITCH_TIME_LIMIT or glitch_count >= max_glitches:
                        break
            else:
                # Single glitch with random timing
                if glitch_count > 0:
                    enable_expr += "+"

                # Vary the duration slightly for more realism
                actual_duration = glitch_duration * random.uniform(  # noqa: S311
                    self.GLITCH_DURATION_VARIATION_MIN, self.GLITCH_DURATION_VARIATION_MAX
                )
                enable_expr += f"between(t,{current_time},{current_time + actual_duration})"

                glitch_count += 1

                # Random interval to next glitch (sometimes longer, sometimes shorter)
                interval_variation = random.uniform(  # noqa: S311
                    self.GLITCH_INTERVAL_VARIATION_MIN, self.GLITCH_INTERVAL_VARIATION_MAX
                )  # 50% to 200% of average
                current_time += avg_interval * interval_variation

            # Advanced filter complex with multiple effects
            # Includes chroma shift, noise, rgbashift, and tear effects with timeline enables
            # Random tear position and offset for each glitch

            # Generate completely random tear position and offset
            tear_position_random = random.uniform(  # noqa: S311
                self.TEAR_POSITION_MIN, self.TEAR_POSITION_MAX
            )  # Random between 10% and 90% of frame
            tear_y_random = f"ih*{tear_position_random}"
            tear_offset_random = random.randint(tear_offset_min, tear_offset_max)  # noqa: S311

            filter_complex = (
                f"scale=720:-2:flags=bicubic,format=yuv420p,"
                f"eq=saturation=0.82:contrast=1.04:gamma=0.98,"
                f"chromashift=cbh={chroma_shift_h}:crh={chroma_shift_v}:edge=smear,"
                f"gblur=sigma={blur_strength},"
                f"tmix=frames={motion_trails}:weights='1 2 1',"
                f"noise=alls={noise_strength}:allf=t+u,"  # spellchecker:disable-line
                f"split=3[main][tear_top][tear_bottom];"
                f"[main]rgbashift=rh={red_h_scaled}:rv={red_v_scaled}:"
                f"gh={green_h_scaled}:gv={green_v_scaled}:"
                f"bh={blue_h_scaled}:bv={blue_v_scaled}:"
                f"enable='{enable_expr}'[rgb_shifted];"
                f"[tear_top]crop=iw:{tear_y_random}:0:0,rgbashift=rh={red_h_scaled}:rv={red_v_scaled}:"
                f"gh={green_h_scaled}:gv={green_v_scaled}:"
                f"bh={blue_h_scaled}:bv={blue_v_scaled}:"
                f"enable='{enable_expr}'[top_shifted];"
                f"[tear_bottom]crop=iw:ih-{tear_y_random}:0:{tear_y_random},rgbashift=rh={red_h_scaled + tear_offset_random}:rv={red_v_scaled}:"
                f"gh={green_h_scaled + tear_offset_random}:gv={green_v_scaled}:"
                f"bh={blue_h_scaled + tear_offset_random}:bv={blue_v_scaled}:"
                f"enable='{enable_expr}'[bottom_shifted];"
                f"[top_shifted][bottom_shifted]vstack[tear_effect];"
                f"[rgb_shifted][tear_effect]overlay=0:0:enable='{enable_expr}'[out]"
            )

        else:
            # Static mode - apply intensity scaling to all shifts
            red_h_scaled = int(red_h * intensity)
            red_v_scaled = int(red_v * intensity)
            green_h_scaled = int(green_h * intensity)
            green_v_scaled = int(green_v * intensity)
            blue_h_scaled = int(blue_h * intensity)
            blue_v_scaled = int(blue_v * intensity)

            # Build RGB shift filter
            filter_complex = (
                f"rgbashift=rh={red_h_scaled}:rv={red_v_scaled}:"
                f"gh={green_h_scaled}:gv={green_v_scaled}:"
                f"bh={blue_h_scaled}:bv={blue_v_scaled}"
            )

        return [
            "ffmpeg",
            "-i",
            input_url,
            "-vf",
            filter_complex,
            "-c:v",
            "libx264",
            "-preset",
            "veryslow",
            "-crf",
            "12",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-y",
            output_path,
        ]

    def _validate_custom_parameters(self) -> list[Exception] | None:  # noqa: C901, PLR0912
        """Validate RGB shift parameters."""
        exceptions = []

        # Validate shift values
        for param_name in [
            "red_horizontal",
            "red_vertical",
            "green_horizontal",
            "green_vertical",
            "blue_horizontal",
            "blue_vertical",
        ]:
            value = self.get_parameter_value(param_name)
            if value is not None and (value < self.MIN_SHIFT or value > self.MAX_SHIFT):
                msg = f"{self.name} - {param_name} must be between {self.MIN_SHIFT} and {self.MAX_SHIFT}, got {value}"
                exceptions.append(ValueError(msg))

        # Validate intensity
        intensity = self.get_parameter_value("intensity")
        if intensity is not None and (intensity < self.MIN_INTENSITY or intensity > self.MAX_INTENSITY):
            msg = f"{self.name} - Intensity must be between {self.MIN_INTENSITY} and {self.MAX_INTENSITY}, got {intensity}"
            exceptions.append(ValueError(msg))

        # Validate glitch parameters
        glitch_freq = self.get_parameter_value("glitch_frequency")
        if glitch_freq is not None and (
            glitch_freq < self.MIN_GLITCH_FREQUENCY or glitch_freq > self.MAX_GLITCH_FREQUENCY
        ):
            msg = f"{self.name} - Glitch frequency must be between {self.MIN_GLITCH_FREQUENCY} and {self.MAX_GLITCH_FREQUENCY}, got {glitch_freq}"
            exceptions.append(ValueError(msg))

        glitch_intensity = self.get_parameter_value("glitch_intensity")
        if glitch_intensity is not None and (
            glitch_intensity < self.MIN_GLITCH_INTENSITY or glitch_intensity > self.MAX_GLITCH_INTENSITY
        ):
            msg = f"{self.name} - Glitch intensity must be between {self.MIN_GLITCH_INTENSITY} and {self.MAX_GLITCH_INTENSITY}, got {glitch_intensity}"
            exceptions.append(ValueError(msg))

        glitch_duration = self.get_parameter_value("glitch_duration")
        if glitch_duration is not None and (
            glitch_duration < self.MIN_GLITCH_DURATION or glitch_duration > self.MAX_GLITCH_DURATION
        ):
            msg = f"{self.name} - Glitch duration must be between {self.MIN_GLITCH_DURATION} and {self.MAX_GLITCH_DURATION}, got {glitch_duration}"
            exceptions.append(ValueError(msg))

        # Validate VHS effect parameters
        noise_strength = self.get_parameter_value("noise_strength")
        if noise_strength is not None and (
            noise_strength < self.MIN_NOISE_STRENGTH or noise_strength > self.MAX_NOISE_STRENGTH
        ):
            msg = f"{self.name} - Noise strength must be between {self.MIN_NOISE_STRENGTH} and {self.MAX_NOISE_STRENGTH}, got {noise_strength}"
            exceptions.append(ValueError(msg))

        chroma_shift_h = self.get_parameter_value("chroma_shift_horizontal")
        if chroma_shift_h is not None and (
            chroma_shift_h < self.MIN_CHROMA_SHIFT or chroma_shift_h > self.MAX_CHROMA_SHIFT
        ):
            msg = f"{self.name} - Chroma shift horizontal must be between {self.MIN_CHROMA_SHIFT} and {self.MAX_CHROMA_SHIFT}, got {chroma_shift_h}"
            exceptions.append(ValueError(msg))

        chroma_shift_v = self.get_parameter_value("chroma_shift_vertical")
        if chroma_shift_v is not None and (
            chroma_shift_v < self.MIN_CHROMA_SHIFT or chroma_shift_v > self.MAX_CHROMA_SHIFT
        ):
            msg = f"{self.name} - Chroma shift vertical must be between {self.MIN_CHROMA_SHIFT} and {self.MAX_CHROMA_SHIFT}, got {chroma_shift_v}"
            exceptions.append(ValueError(msg))

        blur_strength = self.get_parameter_value("blur_strength")
        if blur_strength is not None and (
            blur_strength < self.MIN_BLUR_STRENGTH or blur_strength > self.MAX_BLUR_STRENGTH
        ):
            msg = f"{self.name} - Blur strength must be between {self.MIN_BLUR_STRENGTH} and {self.MAX_BLUR_STRENGTH}, got {blur_strength}"
            exceptions.append(ValueError(msg))

        motion_trails = self.get_parameter_value("motion_trails")
        if motion_trails is not None and (
            motion_trails < self.MIN_MOTION_TRAILS or motion_trails > self.MAX_MOTION_TRAILS
        ):
            msg = f"{self.name} - Motion trails must be between {self.MIN_MOTION_TRAILS} and {self.MAX_MOTION_TRAILS}, got {motion_trails}"
            exceptions.append(ValueError(msg))

        # Validate tear effect parameters
        tear_offset_min = self.get_parameter_value("tear_offset_min")
        if tear_offset_min is not None and (
            tear_offset_min < self.MIN_TEAR_OFFSET or tear_offset_min > self.MAX_TEAR_OFFSET
        ):
            msg = f"{self.name} - Tear offset min must be between {self.MIN_TEAR_OFFSET} and {self.MAX_TEAR_OFFSET}, got {tear_offset_min}"
            exceptions.append(ValueError(msg))

        tear_offset_max = self.get_parameter_value("tear_offset_max")
        if tear_offset_max is not None and (
            tear_offset_max < self.MIN_TEAR_OFFSET or tear_offset_max > self.MAX_TEAR_OFFSET
        ):
            msg = f"{self.name} - Tear offset max must be between {self.MIN_TEAR_OFFSET} and {self.MAX_TEAR_OFFSET}, got {tear_offset_max}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get RGB shift parameters."""
        return {
            "red_horizontal": self.get_parameter_value("red_horizontal"),
            "red_vertical": self.get_parameter_value("red_vertical"),
            "green_horizontal": self.get_parameter_value("green_horizontal"),
            "green_vertical": self.get_parameter_value("green_vertical"),
            "blue_horizontal": self.get_parameter_value("blue_horizontal"),
            "blue_vertical": self.get_parameter_value("blue_vertical"),
            "intensity": self.get_parameter_value("intensity"),
            "glitch_mode": self.get_parameter_value("glitch_mode"),
            "glitch_frequency": self.get_parameter_value("glitch_frequency"),
            "glitch_intensity": self.get_parameter_value("glitch_intensity"),
            "glitch_duration": self.get_parameter_value("glitch_duration"),
            "noise_strength": self.get_parameter_value("noise_strength"),
            "chroma_shift_horizontal": self.get_parameter_value("chroma_shift_horizontal"),
            "chroma_shift_vertical": self.get_parameter_value("chroma_shift_vertical"),
            "blur_strength": self.get_parameter_value("blur_strength"),
            "motion_trails": self.get_parameter_value("motion_trails"),
            "tear_offset_min": self.get_parameter_value("tear_offset_min"),
            "tear_offset_max": self.get_parameter_value("tear_offset_max"),
            "random_seed": self.get_parameter_value("random_seed"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        red_h = kwargs.get("red_horizontal", -self.DEFAULT_SHIFT)
        red_v = kwargs.get("red_vertical", 0)
        green_h = kwargs.get("green_horizontal", self.DEFAULT_SHIFT)
        green_v = kwargs.get("green_vertical", 0)
        blue_h = kwargs.get("blue_horizontal", 0)
        blue_v = kwargs.get("blue_vertical", 0)
        intensity = kwargs.get("intensity", self.DEFAULT_INTENSITY)
        glitch_mode = kwargs.get("glitch_mode", "static")

        suffix = f"_rgbshift_rh{red_h}_rv{red_v}_gh{green_h}_gv{green_v}_bh{blue_h}_bv{blue_v}_i{intensity:.2f}"

        if glitch_mode == "animated":
            glitch_freq = kwargs.get("glitch_frequency", self.DEFAULT_GLITCH_FREQUENCY)
            glitch_intensity = kwargs.get("glitch_intensity", self.DEFAULT_GLITCH_INTENSITY)
            noise_strength = kwargs.get("noise_strength", self.DEFAULT_NOISE_STRENGTH)
            chroma_shift_h = kwargs.get("chroma_shift_horizontal", self.DEFAULT_CHROMA_SHIFT_H)
            chroma_shift_v = kwargs.get("chroma_shift_vertical", self.DEFAULT_CHROMA_SHIFT_V)
            blur_strength = kwargs.get("blur_strength", self.DEFAULT_BLUR_STRENGTH)
            motion_trails = kwargs.get("motion_trails", self.DEFAULT_MOTION_TRAILS)
            tear_offset_min = kwargs.get("tear_offset_min", self.DEFAULT_TEAR_OFFSET_MIN)
            tear_offset_max = kwargs.get("tear_offset_max", self.DEFAULT_TEAR_OFFSET_MAX)
            suffix += f"_animated_f{glitch_freq:.1f}_i{glitch_intensity:.2f}_n{noise_strength}_c{chroma_shift_h}{chroma_shift_v}_b{blur_strength:.1f}_m{motion_trails}_t{tear_offset_min}-{tear_offset_max}"

        return suffix
