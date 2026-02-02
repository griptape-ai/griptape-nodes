"""Status trait for displaying status indicators on parameters."""

from dataclasses import dataclass, field

from griptape_nodes.exe_types.core_types import (
    BaseNodeElement,
    NodeMessagePayload,
    NodeMessageResult,
    ParameterMessage,
    Trait,
)

# Use the same variant types as ParameterMessage for consistency
StatusVariant = ParameterMessage.VariantType


@dataclass(eq=False)
class Status(Trait):
    """A trait that adds a status indicator to a parameter.

    Status indicators show contextual information like warnings, errors, info messages,
    or success states directly on a parameter in the UI.

    Example:
        # Add status when creating a parameter
        param = ParameterString(
            name="api_key",
            traits={Status(variant="warning", message="API key not validated")}
        )

        # Add status with a dismiss button
        param = ParameterString(
            name="result",
            traits={Status(
                variant="success",
                message="Operation complete!",
                show_clear_button=True  # Shows an X button to dismiss
            )}
        )

        # Or add/update status dynamically
        status = Status(variant="info", title="Note", message="Processing...")
        param.add_child(status)

        # Update status properties
        status.variant = "success"
        status.message = "Completed!"

        # Hide/show status
        status.display = False

        # Remove status trait entirely
        param.remove_child(status)
    """

    # Message type constants for frontend communication
    CLEAR_STATUS_MESSAGE_TYPE = "clear_status"
    SET_STATUS_MESSAGE_TYPE = "set_status"
    GET_STATUS_MESSAGE_TYPE = "get_status"
    DISMISS_STATUS_MESSAGE_TYPE = "dismiss_status"

    # Private storage for status properties
    _variant: StatusVariant = field(default="none", init=False)
    _title: str | None = field(default=None, init=False)
    _message: str = field(default="", init=False)
    _display: bool = field(default=True, init=False)
    _show_clear_button: bool = field(default=False, init=False)

    element_id: str = field(default_factory=lambda: "Status")

    def __init__(
        self,
        *,
        variant: StatusVariant = "none",
        title: str | None = None,
        message: str = "",
        display: bool = True,
        show_clear_button: bool = False,
    ) -> None:
        """Initialize a Status trait.

        Args:
            variant: Status variant type (e.g., "info", "warning", "error", "success", "none")
            title: Optional title for the status indicator
            message: Message to display with the status
            display: Whether to show the status indicator (default True)
            show_clear_button: Whether to show a clear/dismiss button (default False).
                When clicked, the button will hide the status by setting display=False.
        """
        super().__init__(element_id="Status")
        self._variant = variant
        self._title = title
        self._message = message
        self._display = display
        self._show_clear_button = show_clear_button

    @property
    def variant(self) -> StatusVariant:
        return self._variant

    @variant.setter
    @BaseNodeElement.emits_update_on_write
    def variant(self, value: StatusVariant) -> None:
        self._variant = value

    @property
    def title(self) -> str | None:
        return self._title

    @title.setter
    @BaseNodeElement.emits_update_on_write
    def title(self, value: str | None) -> None:
        self._title = value

    @property
    def message(self) -> str:
        return self._message

    @message.setter
    @BaseNodeElement.emits_update_on_write
    def message(self, value: str) -> None:
        self._message = value

    @property
    def display(self) -> bool:
        return self._display

    @display.setter
    @BaseNodeElement.emits_update_on_write
    def display(self, value: bool) -> None:
        self._display = value

    @property
    def show_clear_button(self) -> bool:
        return self._show_clear_button

    @show_clear_button.setter
    @BaseNodeElement.emits_update_on_write
    def show_clear_button(self, value: bool) -> None:
        self._show_clear_button = value

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        """Return keys that trigger this trait."""
        return ["status"]

    def ui_options_for_trait(self) -> dict:
        """Generate UI options for the status trait."""
        # Use parent parameter's name so frontend can target the parameter directly
        parameter_name = self._parent.name if self._parent else ""
        return {
            "status": {
                "parameter_name": parameter_name,
                "variant": self.variant,
                "title": self.title if self.title is not None else "",
                "message": self.message,
                "display": self.display,
                "show_clear_button": self.show_clear_button,
            }
        }

    def clear(self) -> None:
        """Clear the status indicator by resetting to defaults."""
        self.variant = "none"
        self.title = None
        self.message = ""
        self.display = True
        self.show_clear_button = False

    def set(
        self,
        variant: StatusVariant | None = None,
        title: str | None = None,
        message: str | None = None,
        *,
        display: bool | None = None,
        show_clear_button: bool | None = None,
    ) -> None:
        """Set multiple status properties at once.

        Args:
            variant: Status variant type (optional)
            title: Title text (optional)
            message: Message text (optional)
            display: Whether to display (optional)
            show_clear_button: Whether to show clear button (optional)
        """
        if variant is not None:
            self.variant = variant
        if title is not None:
            self.title = title
        if message is not None:
            self.message = message
        if display is not None:
            self.display = display
        if show_clear_button is not None:
            self.show_clear_button = show_clear_button

    def _get_status_payload(self) -> NodeMessagePayload:
        """Create a payload containing all current status data."""
        payload = NodeMessagePayload()
        payload.data = {
            "variant": self.variant,
            "title": self.title,
            "message": self.message,
            "display": self.display,
            "show_clear_button": self.show_clear_button,
        }
        return payload

    def _apply_status_from_data(self, data: dict) -> None:
        """Apply status values from a data dictionary."""
        if "variant" in data:
            self.variant = data["variant"]
        if "title" in data:
            self.title = data["title"]
        if "message" in data:
            self.message = data["message"]
        if "display" in data:
            self.display = data["display"]
        if "show_clear_button" in data:
            self.show_clear_button = data["show_clear_button"]

    def on_message_received(self, message_type: str, message: NodeMessagePayload | None) -> NodeMessageResult | None:
        """Handle messages sent to this status trait.

        Args:
            message_type: String indicating the message type
            message: Message payload or None

        Returns:
            NodeMessageResult if handled, None if no handler available
        """
        match message_type.lower():
            case self.CLEAR_STATUS_MESSAGE_TYPE:
                self.clear()
                return NodeMessageResult(
                    success=True,
                    details="Status cleared",
                    response=None,
                    altered_workflow_state=False,
                )

            case self.GET_STATUS_MESSAGE_TYPE:
                return NodeMessageResult(
                    success=True,
                    details="Status retrieved",
                    response=self._get_status_payload(),
                    altered_workflow_state=False,
                )

            case self.SET_STATUS_MESSAGE_TYPE:
                if message is not None and hasattr(message, "data") and isinstance(message.data, dict):
                    self._apply_status_from_data(message.data)
                return NodeMessageResult(
                    success=True,
                    details="Status updated",
                    response=self._get_status_payload(),
                    altered_workflow_state=False,
                )

            case self.DISMISS_STATUS_MESSAGE_TYPE:
                self.display = False
                return NodeMessageResult(
                    success=True,
                    details="Status dismissed",
                    response=None,
                    altered_workflow_state=False,
                )

        # Delegate to parent implementation for unhandled messages
        return super().on_message_received(message_type, message)
