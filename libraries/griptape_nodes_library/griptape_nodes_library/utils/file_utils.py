"""File utility functions for generating filenames and managing file operations."""

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

# Supported text file extensions (based on LoadText node)
SUPPORTED_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".env",
    ".py",
}


def generate_filename(
    node_name: str,
    suffix: str = "",
    extension: str = "png",
    workflow_name: str | None = None,
) -> str:
    """Generate a meaningful filename for any type of node output.

    This utility creates consistent, meaningful filenames across all node types
    (image, video, audio, etc.) with proper sanitization and cache busting.

    Args:
        node_name: Name of the node generating the filename
        suffix: Optional suffix to append to the filename (e.g., "_bloom", "_cropped", "_processed")
        extension: File extension (default: "png")
        workflow_name: Optional workflow name. If not provided, will attempt to get from context

    Returns:
        Generated filename with timestamp for cache busting

    Examples:
        >>> generate_filename("LoadImage", "_processed", "jpg")
        "my_workflow_LoadImage_processed.jpg?t=1703123456"

        >>> generate_filename("VideoProcessor", "_trimmed", "mp4")
        "my_workflow_VideoProcessor_trimmed.mp4?t=1703123456"
    """
    # Get workflow name from context if not provided
    if workflow_name is None:
        try:
            context_manager = GriptapeNodes.ContextManager()
            workflow_name = context_manager.get_current_workflow_name()
        except Exception:
            workflow_name = "unknown_workflow"

    # Clean up names for filename use - keep only alphanumeric, hyphens, and underscores
    workflow_name = "".join(c for c in workflow_name if c.isalnum() or c in ("-", "_")).rstrip()
    node_name = "".join(c for c in node_name if c.isalnum() or c in ("-", "_")).rstrip()

    # Create filename with meaningful structure
    filename = f"{workflow_name}_{node_name}{suffix}.{extension}"

    return filename


def sanitize_filename_component(name: str) -> str:
    """Sanitize a filename component by removing invalid characters.

    Args:
        name: The name to sanitize

    Returns:
        Sanitized name safe for use in filenames
    """
    return "".join(c for c in name if c.isalnum() or c in ("-", "_")).rstrip()
