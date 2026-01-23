import colorsys
import contextlib
import math
from typing import Any, ClassVar, cast

from PIL import Image, ImageDraw

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import save_pil_image_with_named_filename


class CreateColorBars(BaseNode):
    """CreateColorBars Node that generates standard color bar test patterns."""

    # Color bar type choices
    COLOR_BAR_TYPES: ClassVar[list[str]] = [
        "SMPTE 219-100 Bars",
        "SMPTE 75% Bars",
        "SMPTE Bars",
        "SMPTE 219+i Bars",
        "100% Full Field Bars",
        "75% Full Field Bars",
        "75% Bars Over Red",
        "EBU Bars",
        "ARIB 28-100",
        "ARIB 28-75",
        "ARIB 28+i",
        "HD Color Bars",
        "Full Field White",
        "Full Field Blue",
        "Full Field Cyan",
        "Full Field Green",
        "Full Field Magenta",
        "Full Field Red",
        "Full Field Yellow",
        "Zone Plate",
        "Tartan Bars",
        "Stair 5 Step",
        "Stair 5 Step Vert",
        "Stair 10 Step",
        "Stair 10 Step Vert",
        "Y Ramp Up",
        "Y Ramp Down",
        "Vertical Ramp",
        "Legal Chroma Ramp",
        "Full Chroma Ramp",
        "Chroma Ramp",
        "Multi Burst",
        "Pluge",
        "Bowtie",
        "Pathological EG",
        "Pathological PLL",
        "Pathological EG/PLL",
        "AV Delay Pattern 1",
        "AV Delay Pattern 2",
        "Bouncing Box",
    ]

    # Constants for magic numbers
    GRAY_RAMP_MAX_INDEX: ClassVar[int] = 7  # For 8-step grayscale ramp (indices 0-7)
    CHROMA_THRESHOLD_LOW: ClassVar[float] = 0.33  # First threshold for legal chroma ramp
    CHROMA_THRESHOLD_HIGH: ClassVar[float] = 0.66  # Second threshold for legal chroma ramp
    PLUGE_DEFAULT_BAR_COUNT: ClassVar[int] = 3  # Default number of PLUGE bars
    PLUGE_MIN_BAR_COUNT: ClassVar[int] = 2  # Minimum number of PLUGE bars
    PLUGE_MAX_BAR_COUNT: ClassVar[int] = 5  # Maximum number of PLUGE bars

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add color bar type selector
        self.add_parameter(
            ParameterString(
                name="bar_type",
                default_value="SMPTE 219-100 Bars",
                tooltip="Type of color bars to generate",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.COLOR_BAR_TYPES)},
            )
        )

        # Add width parameter
        self.add_parameter(
            ParameterInt(
                name="width",
                default_value=1920,
                tooltip="Width of the color bars image in pixels",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Add height parameter
        self.add_parameter(
            ParameterInt(
                name="height",
                default_value=1080,
                tooltip="Height of the color bars image in pixels",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Add PLUGE-specific parameters (hidden by default)
        self.add_parameter(
            ParameterString(
                name="pluge_ire_setup",
                default_value="NTSC 7.5 IRE",
                tooltip="IRE setup type for PLUGE pattern calibration",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["NTSC 7.5 IRE", "PAL 0 IRE", "RGB Full Range"])},
                ui_options={"hide": True},
            )
        )

        self.add_parameter(
            ParameterInt(
                name="pluge_bar_count",
                default_value=self.PLUGE_DEFAULT_BAR_COUNT,
                tooltip="Number of PLUGE bars (typically 3: super black, black, above black)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"hide": True},
            )
        )

        self.add_parameter(
            ParameterString(
                name="pluge_orientation",
                default_value="vertical",
                tooltip="Orientation of PLUGE bars",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["vertical", "horizontal"])},
                ui_options={"hide": True},
            )
        )

        # Add output image parameter
        self.add_parameter(
            ParameterImage(
                name="image",
                tooltip="Generated color bars image",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=None,
                ui_options={"expander": True},
            )
        )

    def _generate_smpte_219_100_bars(self, width: int, height: int) -> Image.Image:
        """Generate SMPTE 219-100 Bars (HDTV Color Bars)."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # SMPTE 219-100 Bars pattern (7 vertical bars)
        # Colors in order: White, Yellow, Cyan, Green, Magenta, Red, Blue
        colors = [
            (255, 255, 255),  # White
            (255, 255, 0),  # Yellow
            (0, 255, 255),  # Cyan
            (0, 255, 0),  # Green
            (255, 0, 255),  # Magenta
            (255, 0, 0),  # Red
            (0, 0, 255),  # Blue
        ]

        bar_width = width // len(colors)
        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
            draw.rectangle([x1, 0, x2, height], fill=color)

        return img

    def _generate_smpte_75_bars(self, width: int, height: int) -> Image.Image:
        """Generate SMPTE 75% Bars (standard SDTV color bars)."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # SMPTE 75% Bars pattern (7 vertical bars at 75% intensity)
        colors = [
            (191, 191, 191),  # White (75%)
            (191, 191, 0),  # Yellow (75%)
            (0, 191, 191),  # Cyan (75%)
            (0, 191, 0),  # Green (75%)
            (191, 0, 191),  # Magenta (75%)
            (191, 0, 0),  # Red (75%)
            (0, 0, 191),  # Blue (75%)
        ]

        bar_width = width // len(colors)
        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
            draw.rectangle([x1, 0, x2, height], fill=color)

        return img

    def _generate_ebu_bars(self, width: int, height: int) -> Image.Image:
        """Generate EBU Bars (European Broadcasting Union color bars)."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # EBU Bars pattern (8 vertical bars)
        colors = [
            (255, 255, 255),  # White
            (255, 255, 0),  # Yellow
            (0, 255, 255),  # Cyan
            (0, 255, 0),  # Green
            (255, 0, 255),  # Magenta
            (255, 0, 0),  # Red
            (0, 0, 255),  # Blue
            (0, 0, 0),  # Black
        ]

        bar_width = width // len(colors)
        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
            draw.rectangle([x1, 0, x2, height], fill=color)

        return img

    def _generate_smpte_color_bars(self, width: int, height: int) -> Image.Image:
        """Generate SMPTE Color Bars (classic pattern with pluge)."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # SMPTE Color Bars with pluge (8 bars) - 75% intensity per SMPTE ECR 1-1978
        colors = [
            (191, 191, 191),  # White (75%)
            (191, 191, 0),  # Yellow (75%)
            (0, 191, 191),  # Cyan (75%)
            (0, 191, 0),  # Green (75%)
            (191, 0, 191),  # Magenta (75%)
            (191, 0, 0),  # Red (75%)
            (0, 0, 191),  # Blue (75%)
            (16, 16, 16),  # Pluge (super black)
        ]

        bar_width = width // len(colors)
        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
            draw.rectangle([x1, 0, x2, height], fill=color)

        return img

    def _generate_hd_color_bars(self, width: int, height: int) -> Image.Image:
        """Generate HD Color Bars (high definition pattern)."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # HD Color Bars pattern (similar to SMPTE 219-100 but with additional elements)
        # Main bars section (top 2/3)
        colors = [
            (255, 255, 255),  # White
            (255, 255, 0),  # Yellow
            (0, 255, 255),  # Cyan
            (0, 255, 0),  # Green
            (255, 0, 255),  # Magenta
            (255, 0, 0),  # Red
            (0, 0, 255),  # Blue
        ]

        bar_height = int(height * 0.67)
        bar_width = width // len(colors)

        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
            draw.rectangle([x1, 0, x2, bar_height], fill=color)

        # Bottom section with grayscale ramp
        ramp_width = width // 8
        for i in range(8):
            gray_value = int(255 * (i / self.GRAY_RAMP_MAX_INDEX))
            x1 = i * ramp_width
            x2 = (i + 1) * ramp_width if i < self.GRAY_RAMP_MAX_INDEX else width
            draw.rectangle([x1, bar_height, x2, height], fill=(gray_value, gray_value, gray_value))

        return img

    def _generate_full_field(self, color: tuple[int, int, int], width: int, height: int) -> Image.Image:
        """Generate a full field solid color."""
        img = Image.new("RGB", (width, height), color)
        return img

    def _generate_100_full_field_bars(self, width: int, height: int) -> Image.Image:
        """Generate 100% Full Field Bars with bottom section."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # Top section: 7 color bars
        colors = [
            (255, 255, 255),  # White
            (255, 255, 0),  # Yellow
            (0, 255, 255),  # Cyan
            (0, 255, 0),  # Green
            (255, 0, 255),  # Magenta
            (255, 0, 0),  # Red
            (0, 0, 255),  # Blue
        ]

        bar_height = int(height * 0.67)
        bar_width = width // len(colors)

        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
            draw.rectangle([x1, 0, x2, bar_height], fill=color)

        # Bottom section: black, white, black, then small color bars
        bottom_y = bar_height
        small_bar_width = width // 11

        # Black, white, black
        draw.rectangle([0, bottom_y, small_bar_width * 3, height], fill=(0, 0, 0))
        draw.rectangle([small_bar_width, bottom_y, small_bar_width * 2, height], fill=(255, 255, 255))

        # Small color bars
        small_colors = [
            (0, 0, 255),  # Blue
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
            (255, 255, 255),  # White
            (255, 255, 0),  # Yellow
            (255, 0, 0),  # Red
            (0, 255, 0),  # Green
        ]

        for i, color in enumerate(small_colors):
            x1 = small_bar_width * 3 + i * small_bar_width
            x2 = small_bar_width * 3 + (i + 1) * small_bar_width if i < len(small_colors) - 1 else width
            draw.rectangle([x1, bottom_y, x2, height], fill=color)

        return img

    def _generate_75_full_field_bars(self, width: int, height: int) -> Image.Image:
        """Generate 75% Full Field Bars."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # Top section: 7 color bars at 75%
        colors = [
            (191, 191, 191),  # White (75%)
            (191, 191, 0),  # Yellow (75%)
            (0, 191, 191),  # Cyan (75%)
            (0, 191, 0),  # Green (75%)
            (191, 0, 191),  # Magenta (75%)
            (191, 0, 0),  # Red (75%)
            (0, 0, 191),  # Blue (75%)
        ]

        bar_height = int(height * 0.67)
        bar_width = width // len(colors)

        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
            draw.rectangle([x1, 0, x2, bar_height], fill=color)

        # Bottom section similar to 100%
        bottom_y = bar_height
        small_bar_width = width // 11

        draw.rectangle([0, bottom_y, small_bar_width * 3, height], fill=(0, 0, 0))
        draw.rectangle([small_bar_width, bottom_y, small_bar_width * 2, height], fill=(191, 191, 191))

        small_colors = [
            (0, 0, 191),  # Blue (75%)
            (191, 0, 191),  # Magenta (75%)
            (0, 191, 191),  # Cyan (75%)
            (191, 191, 191),  # White (75%)
            (191, 191, 0),  # Yellow (75%)
            (191, 0, 0),  # Red (75%)
            (0, 191, 0),  # Green (75%)
        ]

        for i, color in enumerate(small_colors):
            x1 = small_bar_width * 3 + i * small_bar_width
            x2 = small_bar_width * 3 + (i + 1) * small_bar_width if i < len(small_colors) - 1 else width
            draw.rectangle([x1, bottom_y, x2, height], fill=color)

        return img

    def _generate_75_bars_over_red(self, width: int, height: int) -> Image.Image:
        """Generate 75% Bars Over Red."""
        img = self._generate_75_full_field_bars(width, height)
        draw = ImageDraw.Draw(img)

        # Overlay red on bottom third
        bottom_y = int(height * 0.67)
        draw.rectangle([0, bottom_y, width, height], fill=(191, 0, 0))  # Red (75%)

        # Add white and black bars on top
        bar_width = width // 3
        draw.rectangle([0, bottom_y, bar_width, height], fill=(191, 191, 191))  # White
        draw.rectangle([bar_width * 2, bottom_y, width, height], fill=(0, 0, 0))  # Black

        return img

    def _generate_smpte_bars(self, width: int, height: int) -> Image.Image:
        """Generate SMPTE Bars with bottom section."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # Top section: 7 color bars - 75% intensity per SMPTE ECR 1-1978
        colors = [
            (191, 191, 191),  # White (75%)
            (191, 191, 0),  # Yellow (75%)
            (0, 191, 191),  # Cyan (75%)
            (0, 191, 0),  # Green (75%)
            (191, 0, 191),  # Magenta (75%)
            (191, 0, 0),  # Red (75%)
            (0, 0, 191),  # Blue (75%)
        ]

        bar_height = int(height * 0.67)
        bar_width = width // len(colors)

        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
            draw.rectangle([x1, 0, x2, bar_height], fill=color)

        # Bottom section: black/gray/white bars on left, then small color bars
        bottom_y = bar_height
        left_section_width = width // 4
        small_bar_width = (width - left_section_width) // 7

        # Left section: black, gray, white
        draw.rectangle([0, bottom_y, left_section_width // 3, height], fill=(0, 0, 0))
        draw.rectangle([left_section_width // 3, bottom_y, left_section_width * 2 // 3, height], fill=(128, 128, 128))
        draw.rectangle(
            [left_section_width * 2 // 3, bottom_y, left_section_width, height], fill=(191, 191, 191)
        )  # White at 75%

        # Small color bars - 75% intensity per SMPTE ECR 1-1978
        small_colors = [
            (0, 0, 191),  # Blue (75%)
            (191, 0, 191),  # Magenta (75%)
            (0, 191, 191),  # Cyan (75%)
            (191, 191, 191),  # White (75%)
            (191, 191, 0),  # Yellow (75%)
            (191, 0, 0),  # Red (75%)
            (0, 191, 0),  # Green (75%)
        ]

        for i, color in enumerate(small_colors):
            x1 = left_section_width + i * small_bar_width
            x2 = left_section_width + (i + 1) * small_bar_width if i < len(small_colors) - 1 else width
            draw.rectangle([x1, bottom_y, x2, height], fill=color)

        return img

    def _generate_smpte_219_i_bars(self, width: int, height: int) -> Image.Image:
        """Generate SMPTE 219+i Bars with checkerboard."""
        img = self._generate_smpte_bars(width, height)
        draw = ImageDraw.Draw(img)

        # Add checkerboard pattern on far left of bottom section
        bottom_y = int(height * 0.67)
        checker_size = min(width // 20, (height - bottom_y) // 4)
        checker_x = 0
        checker_y = bottom_y

        for row in range(4):
            for col in range(4):
                x1 = checker_x + col * checker_size
                y1 = checker_y + row * checker_size
                x2 = x1 + checker_size
                y2 = y1 + checker_size
                if (row + col) % 2 == 0:
                    draw.rectangle([x1, y1, x2, y2], fill=(255, 255, 255))
                else:
                    draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0))

        return img

    def _generate_arib_28_100(self, width: int, height: int) -> Image.Image:
        """Generate ARIB 28-100 Bars."""
        return self._generate_smpte_219_i_bars(width, height)  # Similar pattern

    def _generate_arib_28_75(self, width: int, height: int) -> Image.Image:
        """Generate ARIB 28-75 Bars."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # Top section: 7 color bars at 75%
        colors = [
            (191, 191, 191),  # White (75%)
            (191, 191, 0),  # Yellow (75%)
            (0, 191, 191),  # Cyan (75%)
            (0, 191, 0),  # Green (75%)
            (191, 0, 191),  # Magenta (75%)
            (191, 0, 0),  # Red (75%)
            (0, 0, 191),  # Blue (75%)
        ]

        bar_height = int(height * 0.67)
        bar_width = width // len(colors)

        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
            draw.rectangle([x1, 0, x2, bar_height], fill=color)

        # Bottom section with checkerboard
        bottom_y = bar_height
        left_section_width = width // 4
        small_bar_width = (width - left_section_width) // 7

        # Left section: black, gray, white
        draw.rectangle([0, bottom_y, left_section_width // 3, height], fill=(0, 0, 0))
        draw.rectangle([left_section_width // 3, bottom_y, left_section_width * 2 // 3, height], fill=(128, 128, 128))
        draw.rectangle([left_section_width * 2 // 3, bottom_y, left_section_width, height], fill=(191, 191, 191))

        # Checkerboard
        checker_size = min(width // 20, (height - bottom_y) // 4)
        for row in range(4):
            for col in range(4):
                x1 = col * checker_size
                y1 = bottom_y + row * checker_size
                x2 = x1 + checker_size
                y2 = y1 + checker_size
                if (row + col) % 2 == 0:
                    draw.rectangle([x1, y1, x2, y2], fill=(191, 191, 191))
                else:
                    draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0))

        # Small color bars
        small_colors = [
            (0, 0, 191),  # Blue (75%)
            (191, 0, 191),  # Magenta (75%)
            (0, 191, 191),  # Cyan (75%)
            (191, 191, 191),  # White (75%)
            (191, 191, 0),  # Yellow (75%)
            (191, 0, 0),  # Red (75%)
            (0, 191, 0),  # Green (75%)
        ]

        for i, color in enumerate(small_colors):
            x1 = left_section_width + i * small_bar_width
            x2 = left_section_width + (i + 1) * small_bar_width if i < len(small_colors) - 1 else width
            draw.rectangle([x1, bottom_y, x2, height], fill=color)

        return img

    def _generate_arib_28_i(self, width: int, height: int) -> Image.Image:
        """Generate ARIB 28+i Bars."""
        return self._generate_arib_28_100(width, height)

    def _generate_zone_plate(self, width: int, height: int) -> Image.Image:
        """Generate Zone Plate pattern."""
        img = Image.new("RGB", (width, height))
        pixels = cast("Any", img.load())  # Image.load() never returns None for newly created images
        center_x, center_y = width // 2, height // 2
        max_radius = min(width, height) // 2

        for y in range(height):
            for x in range(width):
                dx = x - center_x
                dy = y - center_y
                distance = math.sqrt(dx * dx + dy * dy)
                angle = math.atan2(dy, dx)

                # Create concentric rings and radial lines
                ring_value = int((distance / max_radius * 10) % 2 * 255) if distance < max_radius else 128
                radial_value = int((angle / math.pi * 10) % 2 * 255)

                gray = int((ring_value + radial_value) / 2)
                pixels[x, y] = (gray, gray, gray)

        return img

    def _generate_tartan_bars(self, width: int, height: int) -> Image.Image:
        """Generate Tartan Bars (checkerboard pattern)."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        colors = [
            (255, 0, 0),  # Red
            (0, 255, 0),  # Green
            (0, 0, 255),  # Blue
            (255, 255, 0),  # Yellow
            (0, 255, 255),  # Cyan
            (255, 0, 255),  # Magenta
            (255, 255, 255),  # White
            (0, 0, 0),  # Black
        ]

        tile_size = min(width, height) // 16
        for y in range(0, height, tile_size):
            for x in range(0, width, tile_size):
                color_idx = ((x // tile_size) + (y // tile_size)) % len(colors)
                draw.rectangle([x, y, min(x + tile_size, width), min(y + tile_size, height)], fill=colors[color_idx])

        return img

    def _generate_stair_5_step(self, width: int, height: int) -> Image.Image:
        """Generate 5-step horizontal stair pattern."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        steps = 5
        step_width = width // steps
        for i in range(steps):
            gray_value = int(255 * (i / (steps - 1)))
            x1 = i * step_width
            x2 = (i + 1) * step_width if i < steps - 1 else width
            draw.rectangle([x1, 0, x2, height], fill=(gray_value, gray_value, gray_value))

        return img

    def _generate_stair_5_step_vert(self, width: int, height: int) -> Image.Image:
        """Generate 5-step vertical stair pattern."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        steps = 5
        step_height = height // steps
        for i in range(steps):
            gray_value = int(255 * (i / (steps - 1)))
            y1 = i * step_height
            y2 = (i + 1) * step_height if i < steps - 1 else height
            draw.rectangle([0, y1, width, y2], fill=(gray_value, gray_value, gray_value))

        return img

    def _generate_stair_10_step(self, width: int, height: int) -> Image.Image:
        """Generate 10-step horizontal stair pattern."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        steps = 10
        step_width = width // steps
        for i in range(steps):
            gray_value = int(255 * (i / (steps - 1)))
            x1 = i * step_width
            x2 = (i + 1) * step_width if i < steps - 1 else width
            draw.rectangle([x1, 0, x2, height], fill=(gray_value, gray_value, gray_value))

        return img

    def _generate_stair_10_step_vert(self, width: int, height: int) -> Image.Image:
        """Generate 10-step vertical stair pattern."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        steps = 10
        step_height = height // steps
        for i in range(steps):
            gray_value = int(255 * (i / (steps - 1)))
            y1 = i * step_height
            y2 = (i + 1) * step_height if i < steps - 1 else height
            draw.rectangle([0, y1, width, y2], fill=(gray_value, gray_value, gray_value))

        return img

    def _generate_y_ramp_up(self, width: int, height: int) -> Image.Image:
        """Generate Y Ramp Up (horizontal gradient black to white)."""
        img = Image.new("RGB", (width, height))
        pixels = cast("Any", img.load())  # Image.load() never returns None for newly created images

        for x in range(width):
            gray_value = int(255 * (x / (width - 1)))
            for y in range(height):
                pixels[x, y] = (gray_value, gray_value, gray_value)

        return img

    def _generate_y_ramp_down(self, width: int, height: int) -> Image.Image:
        """Generate Y Ramp Down (horizontal gradient white to black)."""
        img = Image.new("RGB", (width, height))
        pixels = cast("Any", img.load())  # Image.load() never returns None for newly created images

        for x in range(width):
            gray_value = int(255 * (1 - x / (width - 1)))
            for y in range(height):
                pixels[x, y] = (gray_value, gray_value, gray_value)

        return img

    def _generate_vertical_ramp(self, width: int, height: int) -> Image.Image:
        """Generate Vertical Ramp (vertical gradient black to white)."""
        img = Image.new("RGB", (width, height))
        pixels = cast("Any", img.load())  # Image.load() never returns None for newly created images

        for y in range(height):
            gray_value = int(255 * (y / (height - 1)))
            for x in range(width):
                pixels[x, y] = (gray_value, gray_value, gray_value)

        return img

    def _generate_legal_chroma_ramp(self, width: int, height: int) -> Image.Image:
        """Generate Legal Chroma Ramp."""
        img = Image.new("RGB", (width, height))
        pixels = cast("Any", img.load())  # Image.load() never returns None for newly created images

        for x in range(width):
            t = x / (width - 1)
            # Legal chroma range colors
            if t < self.CHROMA_THRESHOLD_LOW:
                r, g, b = int(255 * t * 3), 0, 0
            elif t < self.CHROMA_THRESHOLD_HIGH:
                r, g, b = 255, int(255 * (t - self.CHROMA_THRESHOLD_LOW) * 3), 0
            else:
                r, g, b = (
                    int(255 * (1 - (t - self.CHROMA_THRESHOLD_HIGH) * 3)),
                    255,
                    int(255 * (t - self.CHROMA_THRESHOLD_HIGH) * 3),
                )

            for y in range(height):
                pixels[x, y] = (r, g, b)

        return img

    def _generate_full_chroma_ramp(self, width: int, height: int) -> Image.Image:
        """Generate Full Chroma Ramp."""
        img = Image.new("RGB", (width, height))
        pixels = cast("Any", img.load())  # Image.load() never returns None for newly created images

        for x in range(width):
            hue = (x / width) * 360
            # Convert HSV to RGB
            r, g, b = colorsys.hsv_to_rgb(hue / 360, 1.0, 1.0)
            r, g, b = int(r * 255), int(g * 255), int(b * 255)

            for y in range(height):
                pixels[x, y] = (r, g, b)

        return img

    def _generate_chroma_ramp(self, width: int, height: int) -> Image.Image:
        """Generate Chroma Ramp (color spectrum)."""
        return self._generate_full_chroma_ramp(width, height)

    def _generate_multi_burst(self, width: int, height: int) -> Image.Image:
        """Generate Multi Burst pattern."""
        img = Image.new("RGB", (width, height), (128, 128, 128))
        draw = ImageDraw.Draw(img)

        # Vertical stripes with increasing frequency
        stripe_widths = [width // 4, width // 8, width // 16, width // 32]
        current_x = 0

        for stripe_width in stripe_widths:
            section_width = width // len(stripe_widths)
            for x in range(current_x, current_x + section_width, stripe_width * 2):
                draw.rectangle([x, 0, min(x + stripe_width, current_x + section_width), height], fill=(0, 0, 0))
            current_x += section_width

        return img

    def _generate_pluge(
        self,
        width: int,
        height: int,
        ire_setup: str = "NTSC 7.5 IRE",
        bar_count: int = 3,
        orientation: str = "vertical",
    ) -> Image.Image:
        """Generate PLUGE (Picture Line-up Generation Equipment) pattern for black level calibration.

        Based on 240p test suite specification. Used to adjust brightness/black level.
        Bars represent: super black (below black), black level, and just above black.

        Args:
            width: Image width in pixels
            height: Image height in pixels
            ire_setup: IRE setup type ("NTSC 7.5 IRE", "PAL 0 IRE", or "RGB Full Range")
            bar_count: Number of bars to display (typically 3)
            orientation: Bar orientation ("vertical" or "horizontal")
        """
        img = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Determine IRE values based on setup type
        if ire_setup == "PAL 0 IRE":
            # PAL uses 0 IRE as black level
            super_black_ire = -2.0  # Below black
            black_ire = 0.0  # Black level
            above_black_ire = 2.0  # Just above black
        elif ire_setup == "RGB Full Range":
            # RGB full range uses 0 as black, but we'll use similar relative values
            super_black_ire = -1.0  # Below black (negative IRE equivalent)
            black_ire = 0.0  # Black level
            above_black_ire = 1.5  # Just above black
        else:  # NTSC 7.5 IRE (default)
            # NTSC 7.5 IRE setup
            super_black_ire = 3.5  # Below black level
            black_ire = 7.5  # Black level
            above_black_ire = 11.5  # Just above black

        # IRE to RGB conversion: IRE/100 * 255
        # For negative IRE (below black), clamp to 0
        super_black_rgb = max(0, int(super_black_ire / 100 * 255))
        black_rgb = max(0, int(black_ire / 100 * 255))
        above_black_rgb = max(0, int(above_black_ire / 100 * 255))

        # Create bars based on count (default 3, but allow more)
        bar_count = max(self.PLUGE_MIN_BAR_COUNT, min(bar_count, self.PLUGE_MAX_BAR_COUNT))
        bars = []
        if bar_count >= self.PLUGE_DEFAULT_BAR_COUNT:
            bars = [
                (super_black_rgb, super_black_rgb, super_black_rgb),  # Super black
                (black_rgb, black_rgb, black_rgb),  # Black level
                (above_black_rgb, above_black_rgb, above_black_rgb),  # Just above black
            ]
        elif bar_count == self.PLUGE_MIN_BAR_COUNT:
            bars = [
                (black_rgb, black_rgb, black_rgb),  # Black level
                (above_black_rgb, above_black_rgb, above_black_rgb),  # Just above black
            ]

        # Add additional bars if requested (interpolate between values)
        if bar_count > self.PLUGE_DEFAULT_BAR_COUNT:
            # Add intermediate values between black and above_black
            for i in range(bar_count - 3):
                factor = (i + 1) / (bar_count - 2)
                intermediate_rgb = int(black_rgb + (above_black_rgb - black_rgb) * factor)
                bars.append((intermediate_rgb, intermediate_rgb, intermediate_rgb))

        if orientation == "horizontal":
            # Horizontal bars
            bar_height = height // (bar_count + 2)  # Add spacing
            bar_width = width // 2
            center_x = width // 2
            start_y = (height - (bar_height * bar_count)) // 2

            for i, gray in enumerate(bars):
                y1 = start_y + i * bar_height
                y2 = y1 + bar_height
                x1 = center_x - bar_width // 2
                x2 = center_x + bar_width // 2
                draw.rectangle([x1, y1, x2, y2], fill=gray)
        else:
            # Vertical bars (default)
            bar_width = width // (bar_count + 3)  # Add spacing
            center_x = width // 2
            bar_height = height // 2
            bar_y = (height - bar_height) // 2

            # Draw bars centered horizontally
            start_x = center_x - (bar_width * len(bars)) // 2
            for i, gray in enumerate(bars):
                x1 = start_x + i * bar_width
                x2 = x1 + bar_width
                draw.rectangle([x1, bar_y, x2, bar_y + bar_height], fill=gray)

        return img

    def _generate_bowtie(self, width: int, height: int) -> Image.Image:
        """Generate Bowtie pattern."""
        img = Image.new("RGB", (width, height), (128, 128, 128))
        draw = ImageDraw.Draw(img)

        center_x = width // 2
        stripe_width = width // 20

        # Create bowtie pattern with stripes wider in center
        for x in range(width):
            distance_from_center = abs(x - center_x)
            stripe_freq = max(1, int(stripe_width * (1 + distance_from_center / center_x)))
            if (x // stripe_freq) % 2 == 0:
                draw.rectangle([x, 0, x + 1, height], fill=(0, 0, 0))

        return img

    def _generate_pathological_eg(self, width: int, height: int) -> Image.Image:
        """Generate Pathological EG pattern."""
        return Image.new("RGB", (width, height), (128, 0, 128))  # Purple

    def _generate_pathological_pll(self, width: int, height: int) -> Image.Image:
        """Generate Pathological PLL pattern."""
        return Image.new("RGB", (width, height), (64, 64, 64))  # Dark gray

    def _generate_pathological_eg_pll(self, width: int, height: int) -> Image.Image:
        """Generate Pathological EG/PLL pattern."""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # Top half purple, bottom half dark gray
        draw.rectangle([0, 0, width, height // 2], fill=(128, 0, 128))
        draw.rectangle([0, height // 2, width, height], fill=(64, 64, 64))

        return img

    def _generate_av_delay_pattern_1(self, width: int, height: int) -> Image.Image:
        """Generate AV Delay Pattern 1."""
        img = self._generate_smpte_bars(width, height)
        draw = ImageDraw.Draw(img)

        # Add checkerboard on left
        bottom_y = int(height * 0.67)
        checker_size = min(width // 20, (height - bottom_y) // 4)
        for row in range(4):
            for col in range(4):
                x1 = col * checker_size
                y1 = bottom_y + row * checker_size
                x2 = x1 + checker_size
                y2 = y1 + checker_size
                if (row + col) % 2 == 0:
                    draw.rectangle([x1, y1, x2, y2], fill=(255, 255, 255))
                else:
                    draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0))

        # Add red square in middle of bottom
        red_size = width // 10
        red_x = (width - red_size) // 2
        red_y = bottom_y + (height - bottom_y - red_size) // 2
        draw.rectangle([red_x, red_y, red_x + red_size, red_y + red_size], fill=(255, 0, 0))

        return img

    def _generate_av_delay_pattern_2(self, width: int, height: int) -> Image.Image:
        """Generate AV Delay Pattern 2."""
        img = Image.new("RGB", (width, height), (128, 128, 128))
        draw = ImageDraw.Draw(img)

        # Horizontal white bar in middle
        bar_height = height // 20
        bar_y = (height - bar_height) // 2
        draw.rectangle([0, bar_y, width, bar_y + bar_height], fill=(255, 255, 255))

        # Black square on right end
        square_size = min(width // 10, height // 10)
        square_x = width - square_size - width // 20
        square_y = bar_y - (square_size - bar_height) // 2
        draw.rectangle([square_x, square_y, square_x + square_size, square_y + square_size], fill=(0, 0, 0))

        return img

    def _generate_bouncing_box(self, width: int, height: int) -> Image.Image:
        """Generate Bouncing Box pattern."""
        img = self._generate_smpte_bars(width, height)
        draw = ImageDraw.Draw(img)

        # Red square in bottom middle
        bottom_y = int(height * 0.67)
        box_size = min(width // 8, (height - bottom_y) // 2)
        box_x = (width - box_size) // 2
        box_y = bottom_y + (height - bottom_y - box_size) // 2
        draw.rectangle([box_x, box_y, box_x + box_size, box_y + box_size], fill=(255, 0, 0))

        return img

    def _generate_color_bars(self, bar_type: str, width: int, height: int) -> Image.Image:
        """Generate color bars based on the selected type."""
        # Validate dimensions
        width = max(1, int(width))
        height = max(1, int(height))

        # Handle PLUGE with custom parameters
        if bar_type == "Pluge":
            ire_setup = self.get_parameter_value("pluge_ire_setup") or "NTSC 7.5 IRE"
            bar_count = self.get_parameter_value("pluge_bar_count")
            if bar_count is None:
                bar_count = self.PLUGE_DEFAULT_BAR_COUNT
            bar_count = max(self.PLUGE_MIN_BAR_COUNT, min(int(bar_count), self.PLUGE_MAX_BAR_COUNT))
            orientation = self.get_parameter_value("pluge_orientation") or "vertical"
            return self._generate_pluge(width, height, ire_setup, bar_count, orientation)

        # Map bar types to generator methods
        generators = {
            "SMPTE 219-100 Bars": self._generate_smpte_219_100_bars,
            "SMPTE 75% Bars": self._generate_smpte_75_bars,
            "SMPTE Bars": self._generate_smpte_bars,
            "SMPTE 219+i Bars": self._generate_smpte_219_i_bars,
            "100% Full Field Bars": self._generate_100_full_field_bars,
            "75% Full Field Bars": self._generate_75_full_field_bars,
            "75% Bars Over Red": self._generate_75_bars_over_red,
            "EBU Bars": self._generate_ebu_bars,
            "ARIB 28-100": self._generate_arib_28_100,
            "ARIB 28-75": self._generate_arib_28_75,
            "ARIB 28+i": self._generate_arib_28_i,
            "HD Color Bars": self._generate_hd_color_bars,
            "Full Field White": lambda w, h: self._generate_full_field((255, 255, 255), w, h),
            "Full Field Blue": lambda w, h: self._generate_full_field((0, 0, 255), w, h),
            "Full Field Cyan": lambda w, h: self._generate_full_field((0, 255, 255), w, h),
            "Full Field Green": lambda w, h: self._generate_full_field((0, 255, 0), w, h),
            "Full Field Magenta": lambda w, h: self._generate_full_field((255, 0, 255), w, h),
            "Full Field Red": lambda w, h: self._generate_full_field((255, 0, 0), w, h),
            "Full Field Yellow": lambda w, h: self._generate_full_field((255, 255, 0), w, h),
            "Zone Plate": self._generate_zone_plate,
            "Tartan Bars": self._generate_tartan_bars,
            "Stair 5 Step": self._generate_stair_5_step,
            "Stair 5 Step Vert": self._generate_stair_5_step_vert,
            "Stair 10 Step": self._generate_stair_10_step,
            "Stair 10 Step Vert": self._generate_stair_10_step_vert,
            "Y Ramp Up": self._generate_y_ramp_up,
            "Y Ramp Down": self._generate_y_ramp_down,
            "Vertical Ramp": self._generate_vertical_ramp,
            "Legal Chroma Ramp": self._generate_legal_chroma_ramp,
            "Full Chroma Ramp": self._generate_full_chroma_ramp,
            "Chroma Ramp": self._generate_chroma_ramp,
            "Multi Burst": self._generate_multi_burst,
            "Bowtie": self._generate_bowtie,
            "Pathological EG": self._generate_pathological_eg,
            "Pathological PLL": self._generate_pathological_pll,
            "Pathological EG/PLL": self._generate_pathological_eg_pll,
            "AV Delay Pattern 1": self._generate_av_delay_pattern_1,
            "AV Delay Pattern 2": self._generate_av_delay_pattern_2,
            "Bouncing Box": self._generate_bouncing_box,
        }

        generator = generators.get(bar_type)
        if generator:
            return generator(width, height)
        # Default to SMPTE 219-100 Bars
        return self._generate_smpte_219_100_bars(width, height)

    def _generate_and_set_image(self) -> None:
        """Generate the color bars image and set it as output."""
        # Validate inputs first (failure cases first)
        bar_type = self.get_parameter_value("bar_type")
        if not bar_type:
            bar_type = "SMPTE 219-100 Bars"

        width = self.get_parameter_value("width")
        if width is None:
            width = 1920
        if width <= 0:
            msg = f"{self.name}: Width must be greater than 0, got {width}"
            raise ValueError(msg)

        height = self.get_parameter_value("height")
        if height is None:
            height = 1080
        if height <= 0:
            msg = f"{self.name}: Height must be greater than 0, got {height}"
            raise ValueError(msg)

        # Success path: Generate the color bars image
        image_pil = self._generate_color_bars(bar_type, width, height)

        # Save the image and create URL artifact
        filename = generate_filename(
            node_name=self.name,
            suffix="_color_bars",
            extension="png",
        )
        output_artifact = save_pil_image_with_named_filename(image_pil, filename, "PNG")

        # Set output
        self.parameter_output_values["image"] = output_artifact
        self.publish_update_to_parameter("image", output_artifact)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Generate color bars when input parameters change."""
        # Show/hide PLUGE-specific parameters based on bar_type
        if parameter.name == "bar_type":
            if value == "Pluge":
                self.show_parameter_by_name("pluge_ire_setup")
                self.show_parameter_by_name("pluge_bar_count")
                self.show_parameter_by_name("pluge_orientation")
            else:
                self.hide_parameter_by_name("pluge_ire_setup")
                self.hide_parameter_by_name("pluge_bar_count")
                self.hide_parameter_by_name("pluge_orientation")

        # Generate color bars when relevant parameters change
        if parameter.name in ["bar_type", "width", "height", "pluge_ire_setup", "pluge_bar_count", "pluge_orientation"]:
            # If generation fails (e.g., invalid dimensions), don't update output
            # The error will be caught and handled in process() if needed
            with contextlib.suppress(ValueError):
                self._generate_and_set_image()

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Generate the color bars image."""
        self._generate_and_set_image()
