import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from griptape_nodes.exe_types.core_types import NodeMessagePayload, NodeMessageResult, Trait

if TYPE_CHECKING:
    from collections.abc import Callable

# Don't export callback types - let users import explicitly

logger = logging.getLogger("griptape_nodes")


# Type aliases using Literals
ButtonVariant = Literal[
    "default",
    "secondary",
    "destructive",
    "outline",
    "ghost",
    "link",
]

ButtonSize = Literal[
    "default",
    "sm",
    "icon",
]

ButtonState = Literal[
    "normal",
    "disabled",
    "loading",
    "hidden",
]

IconPosition = Literal[
    "left",
    "right",
]


class ButtonDetailsMessagePayload(NodeMessagePayload):
    """Payload containing complete button details and status information."""

    label: str
    variant: str
    size: str
    state: str
    icon: str | None = None
    icon_class: str | None = None
    icon_position: str | None = None
    full_width: bool = False
    loading_label: str | None = None
    loading_icon: str | None = None
    loading_icon_class: str | None = None


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
    label: str = "Button"
    variant: ButtonVariant = "default"
    size: ButtonSize = "default"
    state: ButtonState = "normal"
    icon: str | None = None
    icon_class: str | None = None
    icon_position: IconPosition | None = None
    full_width: bool = False
    loading_label: str | None = None
    loading_icon: str | None = None
    loading_icon_class: str | None = None

    element_id: str = field(default_factory=lambda: "Button")
    on_click_callback: OnClickCallback | None = field(default=None, init=False)
    get_button_state_callback: GetButtonStateCallback | None = field(default=None, init=False)

    def __init__(  # noqa: PLR0913
        self,
        *,
        label: str = "",  # Allows a button with no text.
        variant: ButtonVariant = "secondary",
        size: ButtonSize = "default",
        state: ButtonState = "normal",
        icon: str | None = None,
        icon_class: str | None = None,
        icon_position: IconPosition | None = None,
        full_width: bool = False,
        loading_label: str | None = None,
        loading_icon: str | None = None,
        loading_icon_class: str | None = None,
        on_click: OnClickCallback | None = None,
        get_button_state: GetButtonStateCallback | None = None,
    ) -> None:
        super().__init__(element_id="Button")
        self.label = label
        self.variant = variant
        self.size = size
        self.state = state
        self.icon = icon
        self.icon_class = icon_class
        self.icon_position = icon_position
        self.full_width = full_width
        self.loading_label = loading_label
        self.loading_icon = loading_icon
        self.loading_icon_class = loading_icon_class
        self.on_click_callback = on_click
        self.get_button_state_callback = get_button_state

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["button", "addbutton"]

    def get_button_details(self, state: ButtonState | None = None) -> ButtonDetailsMessagePayload:
        """Create a ButtonDetailsMessagePayload with current or specified button state."""
        return ButtonDetailsMessagePayload(
            label=self.label,
            variant=self.variant,
            size=self.size,
            state=state or self.state,
            icon=self.icon,
            icon_class=self.icon_class,
            icon_position=self.icon_position,
            full_width=self.full_width,
            loading_label=self.loading_label,
            loading_icon=self.loading_icon,
            loading_icon_class=self.loading_icon_class,
        )

    def ui_options_for_trait(self) -> dict:
        """Generate UI options for the button trait with all styling properties."""
        options = {
            "button_label": self.label,
            "variant": self.variant,
            "size": self.size,
            "state": self.state,
            "full_width": self.full_width,
        }

        # Only include icon properties if icon is specified
        if self.icon:
            options["button_icon"] = self.icon
            options["iconPosition"] = self.icon_position or "left"
            if self.icon_class:
                options["icon_class"] = self.icon_class

        # Include loading properties if specified
        if self.loading_label:
            options["loading_label"] = self.loading_label
        if self.loading_icon:
            options["loading_icon"] = self.loading_icon
        if self.loading_icon_class:
            options["loading_icon_class"] = self.loading_icon_class

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
                            details=f"Button '{self.label}' callback failed: {e!s}",
                            response=None,
                        )

                # Log debug message and fall through if no callback specified
                logger.debug("Button '%s' was clicked, but no on_click_callback was specified.", self.label)

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
                            details=f"Button '{self.label}' get_button_state callback failed: {e!s}",
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
            details=f"Button '{self.label}' details retrieved",
            response=button_details,
            altered_workflow_state=False,
        )
