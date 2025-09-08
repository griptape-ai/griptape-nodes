import logging
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.core_types import NodeMessagePayload, NodeMessageResult, Trait

if TYPE_CHECKING:
    from collections.abc import Callable

# Don't export callback types - let users import explicitly

logger = logging.getLogger("griptape_nodes")


class ButtonVariant(StrEnum):
    """Button visual variants following shadcn design system."""

    DEFAULT = auto()  # Primary/main button (blue in shadcn)
    SECONDARY = auto()  # Muted gray button
    DESTRUCTIVE = auto()  # Red/danger button
    OUTLINE = auto()  # Border only button
    GHOST = auto()  # Minimal/transparent button
    LINK = auto()  # Text link style button


class ButtonSize(StrEnum):
    """Button sizes following shadcn design system."""

    DEFAULT = auto()  # Regular/standard size
    SM = auto()  # Small size
    ICON = auto()  # Square icon-only size


class ButtonState(StrEnum):
    """Button interaction and visibility states."""

    NORMAL = auto()  # Button is interactive (replaces PRESSABLE)
    DISABLED = auto()  # Button cannot be clicked
    LOADING = auto()  # Button is processing/loading
    HIDDEN = auto()  # Button is not visible/rendered


class IconPosition(StrEnum):
    """Icon positioning within button."""

    LEFT = auto()
    RIGHT = auto()


# Legacy alias for backward compatibility during transition
ButtonStatus = ButtonState


class ButtonDetailsMessagePayload(NodeMessagePayload):
    """Payload containing complete button details and status information."""

    text: str
    variant: str
    size: str
    state: str
    icon: str | None = None
    icon_position: str | None = None


class OnClickMessageResultPayload(NodeMessagePayload):
    """Payload for button click result messages."""

    button_details: ButtonDetailsMessagePayload


@dataclass(eq=False)
class Button(Trait):
    # Specific callback types for better type safety and clarity
    type OnClickCallback = Callable[[Button, ButtonDetailsMessagePayload], NodeMessageResult]
    type GetButtonStateCallback = Callable[[Button, ButtonDetailsMessagePayload], NodeMessageResult]

    # Static message type constants
    ON_CLICK_MESSAGE_TYPE = "on_click"
    GET_BUTTON_STATUS_MESSAGE_TYPE = "get_button_status"

    # Button styling and behavior properties
    text: str = "Button"
    variant: ButtonVariant = ButtonVariant.DEFAULT
    size: ButtonSize = ButtonSize.DEFAULT
    state: ButtonState = ButtonState.NORMAL
    icon: str | None = None
    icon_position: IconPosition | None = None

    element_id: str = field(default_factory=lambda: "Button")
    on_click_callback: OnClickCallback | None = field(default=None, init=False)
    get_button_state_callback: GetButtonStateCallback | None = field(default=None, init=False)

    def __init__(  # noqa: PLR0913
        self,
        *,
        text: str = "Button",
        variant: ButtonVariant = ButtonVariant.DEFAULT,
        size: ButtonSize = ButtonSize.DEFAULT,
        state: ButtonState = ButtonState.NORMAL,
        icon: str | None = None,
        icon_position: IconPosition | None = None,
        on_click: OnClickCallback | None = None,
        get_button_state: GetButtonStateCallback | None = None,
    ) -> None:
        super().__init__(element_id="Button")
        self.text = text
        self.variant = variant
        self.size = size
        self.state = state
        self.icon = icon
        self.icon_position = icon_position
        self.on_click_callback = on_click
        self.get_button_state_callback = get_button_state

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["button", "addbutton"]

    def get_button_details(self, state: ButtonState | None = None) -> ButtonDetailsMessagePayload:
        """Create a ButtonDetailsMessagePayload with current or specified button state."""
        return ButtonDetailsMessagePayload(
            text=self.text,
            variant=self.variant.value,
            size=self.size.value,
            state=(state or self.state).value,
            icon=self.icon,
            icon_position=self.icon_position.value if self.icon_position else None,
        )

    def ui_options_for_trait(self) -> dict:
        """Generate UI options for the button trait with all styling properties."""
        options = {
            "button": True,
            "button_label": self.text,
            "variant": self.variant.value,
            "size": self.size.value,
            "state": self.state.value,
        }

        # Only include icon properties if icon is specified
        if self.icon:
            options["button_icon"] = self.icon
            options["iconPosition"] = (self.icon_position or IconPosition.LEFT).value

        return options

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
                        # Pre-fill button details with current state and pass to callback
                        button_details = self.get_button_details()
                        return self.on_click_callback(self, button_details)
                    except Exception as e:
                        return NodeMessageResult(
                            success=False,
                            details=f"Button '{self.text}' callback failed: {e!s}",
                            response=None,
                        )

                # Log debug message and fall through if no callback specified
                logger.debug("Button '%s' was clicked, but no on_click_callback was specified.", self.text)

            case self.GET_BUTTON_STATUS_MESSAGE_TYPE:
                # Use custom callback if provided, otherwise use default implementation
                if self.get_button_state_callback is not None:
                    try:
                        # Pre-fill button details with current state and pass to callback
                        button_details = self.get_button_details()
                        return self.get_button_state_callback(self, button_details)
                    except Exception as e:
                        return NodeMessageResult(
                            success=False,
                            details=f"Button '{self.text}' get_button_state callback failed: {e!s}",
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
        """Default implementation for get_button_status that returns current button details."""
        button_details = self.get_button_details()

        return NodeMessageResult(
            success=True,
            details=f"Button '{self.text}' details retrieved",
            response=button_details,
            altered_workflow_state=False,
        )
