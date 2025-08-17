"""Color utilities for parsing and converting between different color formats."""

import colorsys
import re
from typing import Any

# Constants for magic numbers
HEX_RGB_LENGTH = 6
HEX_RGBA_LENGTH = 8
MAX_ALPHA = 255
MAX_COLOR_VALUE = 255


def parse_color_to_rgba(color_str: str) -> tuple[int, int, int, int]:  # noqa: PLR0911
    """Parse color string to RGBA tuple.

    Supports multiple color formats:
    - Hex: "#ff0000", "#ff0000ff" (with or without alpha)
    - RGB: "rgb(255, 0, 0)"
    - RGBA: "rgba(255, 0, 0, 1.0)"
    - HSL: "hsl(0, 100%, 50%)"
    - HSLA: "hsla(0, 100%, 50%, 1.0)"
    - Named colors: "red", "blue", "transparent", etc.

    Args:
        color_str: Color string in any supported format

    Returns:
        RGBA tuple with values 0-255 for RGB, 0-255 for alpha

    Raises:
        ValueError: If color format is not supported or invalid
    """
    # Normalize input
    color_str = color_str.strip().lower()

    # Handle hex colors
    if color_str.startswith("#"):
        color_str = color_str[1:]  # Remove #
        if len(color_str) == HEX_RGB_LENGTH:
            # RGB hex
            r = int(color_str[0:2], 16)
            g = int(color_str[2:4], 16)
            b = int(color_str[4:6], 16)
            return (r, g, b, MAX_ALPHA)
        if len(color_str) == HEX_RGBA_LENGTH:
            # RGBA hex
            r = int(color_str[0:2], 16)
            g = int(color_str[2:4], 16)
            b = int(color_str[4:6], 16)
            a = int(color_str[6:8], 16)
            return (r, g, b, a)
        msg = f"Invalid hex color format: {color_str}"
        raise ValueError(msg)

    # Handle RGB format: rgb(r, g, b)
    rgb_match = re.match(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", color_str)
    if rgb_match:
        r = int(rgb_match.group(1))
        g = int(rgb_match.group(2))
        b = int(rgb_match.group(3))
        return (r, g, b, MAX_ALPHA)

    # Handle RGBA format: rgba(r, g, b, a)
    rgba_match = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", color_str)
    if rgba_match:
        r = int(rgba_match.group(1))
        g = int(rgba_match.group(2))
        b = int(rgba_match.group(3))
        a = float(rgba_match.group(4))
        # Convert alpha from 0-1 to 0-255
        a = int(a * MAX_ALPHA)
        return (r, g, b, a)

    # Handle HSL format: hsl(h, s%, l%)
    hsl_match = re.match(r"hsl\((\d+),\s*(\d+)%,\s*(\d+)%\)", color_str)
    if hsl_match:
        h = int(hsl_match.group(1)) / 360.0  # Convert to 0-1
        s = int(hsl_match.group(2)) / 100.0  # Convert to 0-1
        lightness = int(hsl_match.group(3)) / 100.0  # Convert to 0-1
        r, g, b = colorsys.hls_to_rgb(h, lightness, s)
        return (int(r * MAX_COLOR_VALUE), int(g * MAX_COLOR_VALUE), int(b * MAX_COLOR_VALUE), MAX_ALPHA)

    # Handle HSLA format: hsla(h, s%, l%, a)
    hsla_match = re.match(r"hsla\((\d+),\s*(\d+)%,\s*(\d+)%,\s*([\d.]+)\)", color_str)
    if hsla_match:
        h = int(hsla_match.group(1)) / 360.0  # Convert to 0-1
        s = int(hsla_match.group(2)) / 100.0  # Convert to 0-1
        lightness = int(hsla_match.group(3)) / 100.0  # Convert to 0-1
        a = float(hsla_match.group(4))  # Already 0-1
        r, g, b = colorsys.hls_to_rgb(h, lightness, s)
        return (int(r * MAX_COLOR_VALUE), int(g * MAX_COLOR_VALUE), int(b * MAX_COLOR_VALUE), int(a * MAX_ALPHA))

    # Handle named colors
    named_colors = {
        "transparent": (0, 0, 0, 0),
        "black": (0, 0, 0, MAX_ALPHA),
        "white": (MAX_COLOR_VALUE, MAX_COLOR_VALUE, MAX_COLOR_VALUE, MAX_ALPHA),
        "red": (MAX_COLOR_VALUE, 0, 0, MAX_ALPHA),
        "green": (0, 128, 0, MAX_ALPHA),
        "blue": (0, 0, MAX_COLOR_VALUE, MAX_ALPHA),
        "yellow": (MAX_COLOR_VALUE, MAX_COLOR_VALUE, 0, MAX_ALPHA),
        "cyan": (0, MAX_COLOR_VALUE, MAX_COLOR_VALUE, MAX_ALPHA),
        "magenta": (MAX_COLOR_VALUE, 0, MAX_COLOR_VALUE, MAX_ALPHA),
        "gray": (128, 128, 128, MAX_ALPHA),
        "grey": (128, 128, 128, MAX_ALPHA),
        "orange": (MAX_COLOR_VALUE, 165, 0, MAX_ALPHA),
        "purple": (128, 0, 128, MAX_ALPHA),
        "pink": (MAX_COLOR_VALUE, 192, 203, MAX_ALPHA),
        "brown": (165, 42, 42, MAX_ALPHA),
        "lime": (0, MAX_COLOR_VALUE, 0, MAX_ALPHA),
        "navy": (0, 0, 128, MAX_ALPHA),
        "teal": (0, 128, 128, MAX_ALPHA),
        "olive": (128, 128, 0, MAX_ALPHA),
        "maroon": (128, 0, 0, MAX_ALPHA),
        "silver": (192, 192, 192, MAX_ALPHA),
        "gold": (MAX_COLOR_VALUE, 215, 0, MAX_ALPHA),
    }

    if color_str in named_colors:
        return named_colors[color_str]

    # If we get here, the color format is not supported
    msg = f"Unsupported color format: {color_str}"
    raise ValueError(msg)


def rgba_to_hex(rgba: tuple[int, int, int, int]) -> str:
    """Convert RGBA tuple to hex string.

    Args:
        rgba: RGBA tuple with values 0-255

    Returns:
        Hex color string with alpha (e.g., "#ff0000ff")
    """
    r, g, b, a = rgba
    return f"#{r:02x}{g:02x}{b:02x}{a:02x}"


def rgba_to_rgb_hex(rgba: tuple[int, int, int, int]) -> str:
    """Convert RGBA tuple to RGB hex string (ignores alpha).

    Args:
        rgba: RGBA tuple with values 0-255

    Returns:
        RGB hex color string (e.g., "#ff0000")
    """
    r, g, b, _ = rgba
    return f"#{r:02x}{g:02x}{b:02x}"


def rgba_to_rgb_string(rgba: tuple[int, int, int, int]) -> str:
    """Convert RGBA tuple to RGB string.

    Args:
        rgba: RGBA tuple with values 0-255

    Returns:
        RGB string (e.g., "rgb(255, 0, 0)")
    """
    r, g, b, _ = rgba
    return f"rgb({r}, {g}, {b})"


def rgba_to_rgba_string(rgba: tuple[int, int, int, int]) -> str:
    """Convert RGBA tuple to RGBA string.

    Args:
        rgba: RGBA tuple with values 0-255

    Returns:
        RGBA string with alpha 0-1 (e.g., "rgba(255, 0, 0, 1.0)")
    """
    r, g, b, a = rgba
    alpha = a / MAX_ALPHA
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


def rgba_to_hsl(rgba: tuple[int, int, int, int]) -> tuple[int, int, int]:
    """Convert RGBA tuple to HSL tuple.

    Args:
        rgba: RGBA tuple with values 0-255

    Returns:
        HSL tuple with values (h: 0-360, s: 0-100, l: 0-100)
    """
    r, g, b, _ = rgba
    # Normalize to 0-1
    r_norm = r / MAX_COLOR_VALUE
    g_norm = g / MAX_COLOR_VALUE
    b_norm = b / MAX_COLOR_VALUE

    h, lightness, s = colorsys.rgb_to_hls(r_norm, g_norm, b_norm)

    # Convert to degrees and percentages
    h_deg = int(h * 360)
    s_percent = int(s * 100)
    l_percent = int(lightness * 100)

    return (h_deg, s_percent, l_percent)


def rgba_to_hsl_string(rgba: tuple[int, int, int, int]) -> str:
    """Convert RGBA tuple to HSL string.

    Args:
        rgba: RGBA tuple with values 0-255

    Returns:
        HSL string (e.g., "hsl(0, 100%, 50%)")
    """
    h, s, lightness = rgba_to_hsl(rgba)
    return f"hsl({h}, {s}%, {lightness}%)"


def rgba_to_hsla_string(rgba: tuple[int, int, int, int]) -> str:
    """Convert RGBA tuple to HSLA string.

    Args:
        rgba: RGBA tuple with values 0-255

    Returns:
        HSLA string with alpha 0-1 (e.g., "hsla(0, 100%, 50%, 1.0)")
    """
    h, s, lightness = rgba_to_hsl(rgba)
    _, _, _, a = rgba
    alpha = a / MAX_ALPHA
    return f"hsla({h}, {s}%, {lightness}%, {alpha:.2f})"


def rgba_to_named_color(rgba: tuple[int, int, int, int]) -> str | None:
    """Convert RGBA tuple to named color if it matches a standard color.

    Args:
        rgba: RGBA tuple with values 0-255

    Returns:
        Named color string or None if no match found
    """
    named_colors = {
        (0, 0, 0, 0): "transparent",
        (0, 0, 0, MAX_ALPHA): "black",
        (MAX_COLOR_VALUE, MAX_COLOR_VALUE, MAX_COLOR_VALUE, MAX_ALPHA): "white",
        (MAX_COLOR_VALUE, 0, 0, MAX_ALPHA): "red",
        (0, 128, 0, MAX_ALPHA): "green",
        (0, 0, MAX_COLOR_VALUE, MAX_ALPHA): "blue",
        (MAX_COLOR_VALUE, MAX_COLOR_VALUE, 0, MAX_ALPHA): "yellow",
        (0, MAX_COLOR_VALUE, MAX_COLOR_VALUE, MAX_ALPHA): "cyan",
        (MAX_COLOR_VALUE, 0, MAX_COLOR_VALUE, MAX_ALPHA): "magenta",
        (128, 128, 128, MAX_ALPHA): "gray",
        (MAX_COLOR_VALUE, 165, 0, MAX_ALPHA): "orange",
        (128, 0, 128, MAX_ALPHA): "purple",
        (MAX_COLOR_VALUE, 192, 203, MAX_ALPHA): "pink",
        (165, 42, 42, MAX_ALPHA): "brown",
        (0, MAX_COLOR_VALUE, 0, MAX_ALPHA): "lime",
        (0, 0, 128, MAX_ALPHA): "navy",
        (0, 128, 128, MAX_ALPHA): "teal",
        (128, 128, 0, MAX_ALPHA): "olive",
        (128, 0, 0, MAX_ALPHA): "maroon",
        (192, 192, 192, MAX_ALPHA): "silver",
        (MAX_COLOR_VALUE, 215, 0, MAX_ALPHA): "gold",
    }

    return named_colors.get(rgba)


def convert_color_format(color_str: str, target_format: str) -> str:  # noqa: PLR0911
    """Convert color from one format to another.

    Args:
        color_str: Source color string in any supported format
        target_format: Target format ("hex", "rgb", "rgba", "hsl", "hsla", "named")

    Returns:
        Color string in the target format

    Raises:
        ValueError: If target format is not supported
    """
    rgba = parse_color_to_rgba(color_str)

    if target_format == "hex":
        return rgba_to_hex(rgba)
    if target_format == "rgb":
        return rgba_to_rgb_string(rgba)
    if target_format == "rgba":
        return rgba_to_rgba_string(rgba)
    if target_format == "hsl":
        return rgba_to_hsl_string(rgba)
    if target_format == "hsla":
        return rgba_to_hsla_string(rgba)
    if target_format == "named":
        named = rgba_to_named_color(rgba)
        if named:
            return named
        # Fallback to hex if no named color matches
        return rgba_to_hex(rgba)
    msg = f"Unsupported target format: {target_format}"
    raise ValueError(msg)


def is_valid_color(color_str: str) -> bool:
    """Check if a color string is valid.

    Args:
        color_str: Color string to validate

    Returns:
        True if the color string is valid, False otherwise
    """
    try:
        parse_color_to_rgba(color_str)
    except ValueError:
        return False
    else:
        return True


def get_color_info(color_str: str) -> dict[str, Any]:
    """Get comprehensive information about a color.

    Args:
        color_str: Color string in any supported format

    Returns:
        Dictionary containing color information in various formats
    """
    rgba = parse_color_to_rgba(color_str)
    r, g, b, a = rgba

    return {
        "rgba": rgba,
        "rgb": (r, g, b),
        "alpha": a,
        "alpha_percent": round((a / MAX_ALPHA) * 100, 1),
        "hex": rgba_to_hex(rgba),
        "rgb_hex": rgba_to_rgb_hex(rgba),
        "rgb_string": rgba_to_rgb_string(rgba),
        "rgba_string": rgba_to_rgba_string(rgba),
        "hsl": rgba_to_hsl(rgba),
        "hsl_string": rgba_to_hsl_string(rgba),
        "hsla_string": rgba_to_hsla_string(rgba),
        "named": rgba_to_named_color(rgba),
        "is_transparent": a == 0,
        "is_opaque": a == MAX_ALPHA,
    }
