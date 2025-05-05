from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode


class DisplayVideo(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="video_url",
                type="str",
                input_types=["str"],
                default_value="",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Video URL",
                ui_options={"display_video": True},
            )
        )

    def process(self) -> None:
        pass