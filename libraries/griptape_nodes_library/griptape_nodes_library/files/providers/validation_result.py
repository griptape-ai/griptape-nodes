from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderValidationResult:
    """Result of provider validation containing all updates or error information.

    Always contains all fields - LoadFile uses is_success/is_failure to determine
    whether to apply the updates or show the error messages.
    """

    # The validated file artifact (ImageUrlArtifact, etc.) ready for use
    artifact: Any

    # Internal serving URL for the file (http://localhost:8124/static-uploads/...)
    internal_url: str

    # User-friendly display path shown in the path parameter
    path: str

    # Updates for provider-specific parameters (e.g., mask extraction results)
    dynamic_parameter_updates: dict[str, Any]

    # List of error messages if validation failed (empty list means success)
    error_messages: list[str]

    def __init__(
        self,
        artifact: Any = None,
        internal_url: str = "",
        path: str = "",
        dynamic_parameter_updates: dict[str, Any] | None = None,
        error_messages: list[str] | None = None,
    ) -> None:
        """Initialize validation result with all fields."""
        self.artifact = artifact
        self.internal_url = internal_url
        self.path = path
        self.dynamic_parameter_updates = dynamic_parameter_updates or {}
        self.error_messages = error_messages or []

    @property
    def is_success(self) -> bool:
        """Check if validation was successful (no error messages)."""
        return not self.error_messages

    @property
    def is_failure(self) -> bool:
        """Check if validation failed (has error messages)."""
        return bool(self.error_messages)
