"""Utility functions for artifact provider operations."""


def normalize_friendly_name_to_key(friendly_name: str) -> str:
    """Normalize a friendly name to a config key component.

    Converts friendly names (e.g., "Image", "Standard Thumbnail Generation")
    to normalized config key components (e.g., "image", "standard_thumbnail_generation").

    This normalization is used throughout the config system to ensure consistent
    key formatting across providers, generators, and manager logic.

    Args:
        friendly_name: Human-readable name with possible spaces and mixed case

    Returns:
        Lowercased name with spaces replaced by underscores

    Examples:
        >>> normalize_friendly_name_to_key("Image")
        "image"
        >>> normalize_friendly_name_to_key("Standard Thumbnail Generation")
        "standard_thumbnail_generation"
    """
    return friendly_name.lower().replace(" ", "_")
