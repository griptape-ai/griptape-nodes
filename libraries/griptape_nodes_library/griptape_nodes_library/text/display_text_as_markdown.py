from typing import Any

from griptape_nodes_library.text.display_text import DisplayText


class DisplayTextAsMarkdown(DisplayText):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        text_param = self.get_parameter_by_name("text")
        if text_param:
            ui_options = text_param.ui_options
            ui_options["markdown"] = True
            text_param.ui_options = ui_options
