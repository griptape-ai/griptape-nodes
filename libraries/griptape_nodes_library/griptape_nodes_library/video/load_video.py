from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.video_utils import dict_to_video_url_artifact


class LoadVideo(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Video"
        self.description = "Load a video"
        video_parameter = Parameter(
            name="video",
            input_types=["VideoArtifact", "VideoUrlArtifact"],
            type="VideoArtifact",
            output_type="VideoUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True},
            tooltip="The video that has been loaded.",
        )
        self.add_parameter(video_parameter)

    def process(self) -> None:
        video = self.get_parameter_value("video")

        if isinstance(video, dict):
            video_artifact = dict_to_video_url_artifact(video)
        else:
            video_artifact = video

        self.parameter_output_values["video"] = video_artifact
