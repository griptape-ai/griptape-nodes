"""Shared validation utilities for LTX-2 pipelines."""


def is_valid_num_frames(num_frames: int) -> bool:
    """Check if num_frames follows the LTX-2 pattern (n * 8) + 1.

    LTX-2 requires frame counts of 9, 17, 25, 33, 41, 49, 57, 65, 73, 81, 89, 97, etc.
    """
    return (num_frames - 1) % 8 == 0 and num_frames >= 9  # noqa: PLR2004


def get_valid_num_frames_hint(num_frames: int) -> str:
    """Get a hint for valid num_frames values near the given value."""
    # Find the nearest valid values
    lower = ((num_frames - 1) // 8) * 8 + 1
    upper = lower + 8
    lower = max(lower, 9)
    return f"Valid values: {lower}, {upper}, etc. (pattern: (n x 8) + 1 where n >= 1)"


def is_valid_dimension(value: int) -> bool:
    """Check if a dimension (width or height) is divisible by 32.

    LTX-2 requires width and height to be divisible by 32.
    """
    return value % 32 == 0


def get_nearest_valid_dimension(value: int) -> int:
    """Get the nearest dimension value divisible by 32."""
    return round(value / 32) * 32
