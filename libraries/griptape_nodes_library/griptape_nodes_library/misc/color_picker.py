from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.color_picker import ColorPicker


class ColorPickerNode(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Add flag to prevent sync during initialization
        self._initializing = True

        self.add_parameter(
            Parameter(
                name="hex",
                default_value="#ffffff",
                type="str",
                tooltip="Hex color like #ffffff or #fffffa",
                traits={ColorPicker(format="hex")},
            )
        )
        self.add_parameter(
            Parameter(
                name="hexa",
                default_value="#ffffffff",
                type="str",
                tooltip="Hexa color like #ffffffff or #ffff",
                traits={ColorPicker(format="hexa")},
            )
        )
        self.add_parameter(
            Parameter(
                name="rgb",
                default_value="rgb(255, 255, 255)",
                type="str",
                tooltip="RGB color like rgb(255, 255, 255)",
                traits={ColorPicker(format="rgb")},
            )
        )
        self.add_parameter(
            Parameter(
                name="rgba",
                default_value="rgba(255, 255, 255, 1.0)",
                type="str",
                tooltip="RGBA color like rgba(255, 255, 255, 1.0)",
                traits={ColorPicker(format="rgba")},
            )
        )
        self.add_parameter(
            Parameter(
                name="hsl",
                default_value="hsl(0, 0%, 100%)",
                type="str",
                tooltip="HSL color like hsl(0, 0%, 100%)",
                traits={ColorPicker(format="hsl")},
            )
        )
        self.add_parameter(
            Parameter(
                name="hsla",
                default_value="hsla(0, 0%, 100%, 1.0)",
                type="str",
                tooltip="HSLA color like hsla(0, 0%, 100%, 1.0)",
                traits={ColorPicker(format="hsla")},
            )
        )
        self.add_parameter(
            Parameter(
                name="hsv",
                default_value="hsv(0, 0%, 100%)",
                type="str",
                tooltip="HSV color like hsv(0, 0%, 100%)",
                traits={ColorPicker(format="hsv")},
            )
        )
        self.add_parameter(
            Parameter(
                name="hsva",
                default_value="hsva(0, 0%, 100%, 1.0)",
                type="str",
                tooltip="HSVA color like hsva(0, 0%, 100%, 1.0)",
                traits={ColorPicker(format="hsva")},
            )
        )

    def process(self) -> None:
        pass
