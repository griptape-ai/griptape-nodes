"""Color utilities for parsing and converting between different color formats."""

import colorsys
import re
from typing import Any

# Constants for magic numbers
HEX_RGB_LENGTH = 6
HEX_RGBA_LENGTH = 8
MAX_ALPHA = 255
MAX_COLOR_VALUE = 255
MAX_HUE = 360
MAX_PERCENT = 100
MAX_HUE_NORMALIZED = 1.0
MAX_ALPHA_NORMALIZED = 1.0

# Compiled regex patterns for better performance with case-insensitive flags
RGB_PATTERN = re.compile(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", re.IGNORECASE)
RGBA_PATTERN = re.compile(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", re.IGNORECASE)
HSL_PATTERN = re.compile(r"hsl\((\d+),\s*(\d+)%,\s*(\d+)%\)", re.IGNORECASE)
HSLA_PATTERN = re.compile(r"hsla\((\d+),\s*(\d+)%,\s*(\d+)%,\s*([\d.]+)\)", re.IGNORECASE)

# Named color mappings to avoid duplication
NAMED_COLORS = {
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


def _validate_hsl_values(h_val: int, s_val: int, l_val: int, color_str: str) -> None:
    """Validate HSL values are within correct ranges.

    Args:
        h_val: Hue value (0-360)
        s_val: Saturation value (0-100)
        l_val: Lightness value (0-100)
        color_str: Original color string for error messages

    Raises:
        ValueError: If any HSL value is out of range
    """
    if not (0 <= h_val <= MAX_HUE):
        msg = f"Hue value must be between 0 and {MAX_HUE}: {color_str}"
        raise ValueError(msg)
    if not (0 <= s_val <= MAX_PERCENT):
        msg = f"Saturation value must be between 0 and {MAX_PERCENT}: {color_str}"
        raise ValueError(msg)
    if not (0 <= l_val <= MAX_PERCENT):
        msg = f"Lightness value must be between 0 and {MAX_PERCENT}: {color_str}"
        raise ValueError(msg)


def _validate_alpha_value(alpha: float, color_str: str, *, allow_255_range: bool = False) -> None:
    """Validate alpha value is within correct range.

    Args:
        alpha: Alpha value (0.0-1.0 or 0-255 if allow_255_range=True)
        color_str: Original color string for error messages
        allow_255_range: If True, allows 0-255 range instead of 0.0-1.0

    Raises:
        ValueError: If alpha value is out of range
    """
    if allow_255_range:
        if not (0 <= alpha <= MAX_ALPHA):
            msg = f"Alpha value must be between 0 and {MAX_ALPHA}: {color_str}"
            raise ValueError(msg)
    elif not (0.0 <= alpha <= MAX_ALPHA_NORMALIZED):
        msg = f"Alpha value must be between 0.0 and {MAX_ALPHA_NORMALIZED}: {color_str}"
        raise ValueError(msg)


def validate_alpha_value_auto(alpha: float, color_str: str) -> None:
    """Automatically detect and validate alpha value range.

    Detects whether alpha is in 0.0-1.0 or 0-255 range based on the value.
    Values <= 1.0 are treated as 0.0-1.0 range, values > 1.0 are treated as 0-255 range.

    Args:
        alpha: Alpha value (automatically detected range)
        color_str: Original color string for error messages

    Raises:
        ValueError: If alpha value is out of range
    """
    if alpha <= 1.0:
        # Treat as 0.0-1.0 range
        if not (0.0 <= alpha <= MAX_ALPHA_NORMALIZED):
            msg = f"Alpha value must be between 0.0 and {MAX_ALPHA_NORMALIZED}: {color_str}"
            raise ValueError(msg)
    # Treat as 0-255 range
    elif not (0 <= alpha <= MAX_ALPHA):
        msg = f"Alpha value must be between 0 and {MAX_ALPHA}: {color_str}"
        raise ValueError(msg)


def _parse_hex_color(color_str: str) -> tuple[int, int, int, int]:
    """Parse hex color string to RGBA tuple."""
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


def _parse_rgb_color(color_str: str) -> tuple[int, int, int, int] | None:
    """Parse RGB color string to RGBA tuple."""
    rgb_match = RGB_PATTERN.match(color_str)
    if rgb_match:
        try:
            r = int(rgb_match.group(1))
            g = int(rgb_match.group(2))
            b = int(rgb_match.group(3))
        except (ValueError, TypeError) as e:
            msg = f"Invalid numeric values in RGB format: {color_str}"
            raise ValueError(msg) from e
        # Validate RGB values are in 0-255 range
        if not (0 <= r <= MAX_COLOR_VALUE and 0 <= g <= MAX_COLOR_VALUE and 0 <= b <= MAX_COLOR_VALUE):
            msg = f"RGB values must be between 0 and {MAX_COLOR_VALUE}: rgb({r}, {g}, {b})"
            raise ValueError(msg)
        return (r, g, b, MAX_ALPHA)
    return None


def _parse_rgba_color(color_str: str) -> tuple[int, int, int, int] | None:
    """Parse RGBA color string to RGBA tuple."""
    rgba_match = RGBA_PATTERN.match(color_str)
    if rgba_match:
        try:
            r = int(rgba_match.group(1))
            g = int(rgba_match.group(2))
            b = int(rgba_match.group(3))
            a = float(rgba_match.group(4))
        except (ValueError, TypeError) as e:
            msg = f"Invalid numeric values in RGBA format: {color_str}"
            raise ValueError(msg) from e
        # Validate RGB values are in 0-255 range
        if not (0 <= r <= MAX_COLOR_VALUE and 0 <= g <= MAX_COLOR_VALUE and 0 <= b <= MAX_COLOR_VALUE):
            msg = f"RGB values must be between 0 and {MAX_COLOR_VALUE}: rgba({r}, {g}, {b}, {a})"
            raise ValueError(msg)
        # Validate alpha value is in 0-1 range
        _validate_alpha_value(a, color_str)
        # Convert alpha from 0-1 to 0-255
        a = int(a * MAX_ALPHA)
        return (r, g, b, a)
    return None


def _parse_hsl_color(color_str: str) -> tuple[int, int, int, int] | None:
    """Parse HSL color string to RGBA tuple."""
    hsl_match = HSL_PATTERN.match(color_str)
    if hsl_match:
        try:
            h_val = int(hsl_match.group(1))
            s_val = int(hsl_match.group(2))
            l_val = int(hsl_match.group(3))
        except (ValueError, TypeError) as e:
            msg = f"Invalid numeric values in HSL format: {color_str}"
            raise ValueError(msg) from e
        # Validate HSL values are in correct ranges
        _validate_hsl_values(h_val, s_val, l_val, color_str)
        h = h_val / MAX_HUE  # Convert to 0-1
        s = s_val / MAX_PERCENT  # Convert to 0-1
        lightness = l_val / MAX_PERCENT  # Convert to 0-1
        r, g, b = colorsys.hls_to_rgb(h, lightness, s)
        return (int(r * MAX_COLOR_VALUE), int(g * MAX_COLOR_VALUE), int(b * MAX_COLOR_VALUE), MAX_ALPHA)
    return None


def _parse_hsla_color(color_str: str) -> tuple[int, int, int, int] | None:
    """Parse HSLA color string to RGBA tuple."""
    hsla_match = HSLA_PATTERN.match(color_str)
    if hsla_match:
        try:
            h_val = int(hsla_match.group(1))
            s_val = int(hsla_match.group(2))
            l_val = int(hsla_match.group(3))
            a = float(hsla_match.group(4))
        except (ValueError, TypeError) as e:
            msg = f"Invalid numeric values in HSLA format: {color_str}"
            raise ValueError(msg) from e
        # Validate HSL values are in correct ranges
        _validate_hsl_values(h_val, s_val, l_val, color_str)
        # Validate alpha value is in 0-1 range
        _validate_alpha_value(a, color_str)
        h = h_val / MAX_HUE  # Convert to 0-1
        s = s_val / MAX_PERCENT  # Convert to 0-1
        lightness = l_val / MAX_PERCENT  # Convert to 0-1
        r, g, b = colorsys.hls_to_rgb(h, lightness, s)
        return (int(r * MAX_COLOR_VALUE), int(g * MAX_COLOR_VALUE), int(b * MAX_COLOR_VALUE), int(a * MAX_ALPHA))
    return None


def _get_named_color(color_str: str) -> tuple[int, int, int, int] | None:
    """Get RGBA tuple for named color."""
    return NAMED_COLORS.get(color_str)


def parse_color_to_rgba(color_str: str) -> tuple[int, int, int, int]:
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
    # Normalize input (case-insensitive regex patterns handle RGB/HSL formats)
    color_str = color_str.strip().lower()

    # Handle hex colors
    if color_str.startswith("#"):
        return _parse_hex_color(color_str)

    # Try parsing different color formats
    result = _parse_rgb_color(color_str)
    if result is not None:
        return result

    result = _parse_rgba_color(color_str)
    if result is not None:
        return result

    result = _parse_hsl_color(color_str)
    if result is not None:
        return result

    result = _parse_hsla_color(color_str)
    if result is not None:
        return result

    # Handle named colors
    result = _get_named_color(color_str)
    if result is not None:
        return result

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
    h_deg = int(h * MAX_HUE)
    s_percent = int(s * MAX_PERCENT)
    l_percent = int(lightness * MAX_PERCENT)

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
    # Create reverse mapping from RGBA tuples to color names
    rgba_to_name = {rgba_tuple: name for name, rgba_tuple in NAMED_COLORS.items()}
    return rgba_to_name.get(rgba)


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
        "alpha_percent": round((a / MAX_ALPHA) * MAX_PERCENT, 1),
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
