from griptape_nodes.exe_types.core_types import ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.compare import Compare
from griptape_nodes.traits.clamp import Clamp

class CompareImages(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "Image"
        self.description = "Compare two images"

        self.add_parameter(
            ParameterList(
                name="images",
                input_types=["ImageArtifact"],
                tooltip="Images to compare",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
            )
        )

        # Add both traits to the images parameter
        images_parameter = self.get_parameter_by_name("images")
        if images_parameter is not None:
            images_parameter.add_trait(Compare())
            images_parameter.add_trait(Clamp(0, 2))

    def process(self) -> None:
        images = self.parameter_values.get("images", [])
        
        if len(images) != 2:
            logger.error("Exactly two images are required for comparison")
            return
