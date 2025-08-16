from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode


class ColorPicker(BaseNode):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="color_picker",
                type="CustomWidget",
                default_value='{"color": "#000000"}',
                tooltip="This is a custom widget that allows you to pick a color.",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"srcdoc": Path(__file__).parent.joinpath("widget.html").read_text()},
            )
        )

        self.add_parameter(
            Parameter(
                name="color",
                type="str",
                default_value="black",
                tooltip="output color",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        pass
