import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from griptape_nodes.exe_types.core_types import ElementMessageCallback, Trait

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import NodeMessageResult

logger = logging.getLogger("griptape_nodes")


@dataclass(eq=False)
class Button(Trait):
    # Static message type constants
    ON_CLICK_MESSAGE_TYPE = "on_click"

    type: str = field(default_factory=lambda: "Generic")
    element_id: str = field(default_factory=lambda: "Button")
    on_click_callback: ElementMessageCallback | None = field(default=None, init=False)

    def __init__(self, button_type: str | None = None, on_click: ElementMessageCallback | None = None) -> None:
        super().__init__(element_id="Button")
        if button_type:
            self.type = button_type
        self.on_click_callback = on_click

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["button", "addbutton"]

    def ui_options_for_trait(self) -> dict:
        return {"button": self.type}

    def on_message_received(self, message_type: str, message: Any) -> "NodeMessageResult | None":
        """Handle messages sent to this button trait.

        Args:
            message_type: String indicating the message type for parsing
            message: Message payload

        Returns:
            NodeMessageResult | None: Result if handled, None if no handler available
        """
        from griptape_nodes.exe_types.node_types import NodeMessageResult

        match message_type.lower():
            case self.ON_CLICK_MESSAGE_TYPE:
                if self.on_click_callback is not None:
                    try:
                        return self.on_click_callback(message_type, message)
                    except Exception as e:
                        return NodeMessageResult(
                            success=False,
                            details=f"Button '{self.type}' callback failed: {e!s}",
                            response=None,
                        )

                # Log debug message and fall through if no callback specified
                logger.debug("Button '%s' was clicked, but no on_click_callback was specified.", self.type)

        # Delegate to parent implementation for unhandled messages or no callback
        return super().on_message_received(message_type, message)
