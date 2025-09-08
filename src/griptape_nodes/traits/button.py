import logging
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.core_types import NodeMessagePayload, NodeMessageResult, Trait

if TYPE_CHECKING:
    from collections.abc import Callable

# Specific callback types for better type safety and clarity
type OnClickCallback = Callable[["Button"], NodeMessageResult]
type GetButtonStatusCallback = Callable[["Button"], NodeMessageResult]

# Don't export callback types - let users import explicitly

logger = logging.getLogger("griptape_nodes")


class ButtonStatus(StrEnum):
    """Enumeration of possible button states."""

    PRESSABLE = auto()
    PRESSED = auto()
    HIDDEN = auto()
    DISABLED = auto()


class ButtonDetailsMessagePayload(NodeMessagePayload):
    """Payload containing button details and status information."""

    button_name: str
    status: ButtonStatus


class OnClickMessageResultPayload(NodeMessagePayload):
    """Payload for button click result messages."""

    button_details: ButtonDetailsMessagePayload


@dataclass(eq=False)
class Button(Trait):
    # Static message type constants
    ON_CLICK_MESSAGE_TYPE = "on_click"
    GET_BUTTON_STATUS_MESSAGE_TYPE = "get_button_status"

    type: str = field(default_factory=lambda: "Generic")
    element_id: str = field(default_factory=lambda: "Button")
    on_click_callback: OnClickCallback | None = field(default=None, init=False)
    get_button_status_callback: GetButtonStatusCallback | None = field(default=None, init=False)

    def __init__(
        self,
        button_type: str | None = None,
        on_click: OnClickCallback | None = None,
        get_button_status: GetButtonStatusCallback | None = None,
    ) -> None:
        super().__init__(element_id="Button")
        if button_type:
            self.type = button_type
        self.on_click_callback = on_click
        self.get_button_status_callback = get_button_status

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["button", "addbutton"]

    def ui_options_for_trait(self) -> dict:
        return {"button": self.type}

    def on_message_received(self, message_type: str, message: NodeMessagePayload | None) -> NodeMessageResult | None:
        """Handle messages sent to this button trait.

        Args:
            message_type: String indicating the message type for parsing
            message: Message payload as NodeMessagePayload or None

        Returns:
            NodeMessageResult | None: Result if handled, None if no handler available
        """
        match message_type.lower():
            case self.ON_CLICK_MESSAGE_TYPE:
                if self.on_click_callback is not None:
                    try:
                        # Call the callback and return result directly
                        return self.on_click_callback(self)
                    except Exception as e:
                        return NodeMessageResult(
                            success=False,
                            details=f"Button '{self.type}' callback failed: {e!s}",
                            response=None,
                        )

                # Log debug message and fall through if no callback specified
                logger.debug("Button '%s' was clicked, but no on_click_callback was specified.", self.type)

            case self.GET_BUTTON_STATUS_MESSAGE_TYPE:
                # Use custom callback if provided, otherwise use default implementation
                if self.get_button_status_callback is not None:
                    try:
                        # Call the callback and return result directly
                        return self.get_button_status_callback(self)
                    except Exception as e:
                        return NodeMessageResult(
                            success=False,
                            details=f"Button '{self.type}' get_button_status callback failed: {e!s}",
                            response=None,
                        )
                else:
                    return self._default_get_button_status(message_type, message)

        # Delegate to parent implementation for unhandled messages or no callback
        return super().on_message_received(message_type, message)

    def _default_get_button_status(
        self,
        message_type: str,  # noqa: ARG002
        message: NodeMessagePayload | None,  # noqa: ARG002
    ) -> NodeMessageResult:
        """Default implementation for get_button_status that returns PRESSABLE status."""
        button_details = ButtonDetailsMessagePayload(button_name=self.type, status=ButtonStatus.PRESSABLE)

        return NodeMessageResult(
            success=True,
            details=f"Button '{self.type}' status: {ButtonStatus.PRESSABLE.value}",
            response=button_details,
            altered_workflow_state=False,
        )
