from collections import OrderedDict

from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import image_artifact_to_pil

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options


class UnionOneFluxControlNetParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._control_mode_by_name = OrderedDict()
        self._control_mode_by_name["canny"] = 0
        self._control_mode_by_name["tile"] = 1
        self._control_mode_by_name["depth"] = 2
        self._control_mode_by_name["blur"] = 3
        self._control_mode_by_name["gray"] = 5

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="controlnet_conditioning_scale",
                default_value=0.7,
                input_types=["float"],
                type="float",
                tooltip="controlnet_conditioning_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_guidance_end",
                default_value=0.8,
                input_types=["float"],
                type="float",
                tooltip="control_guidance_end",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_mode",
                default_value=next(iter(self._control_mode_by_name.keys())),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(self._control_mode_by_name.keys()),
                    )
                },
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="control_image",
            )
        )

    def get_control_image_pil(self) -> Image:
        control_image_artifact = self._node.get_parameter_value("control_image")
        if isinstance(control_image_artifact, ImageUrlArtifact):
            control_image_artifact = ImageLoader().parse(control_image_artifact.to_bytes())
        control_image_pil = image_artifact_to_pil(control_image_artifact)
        return control_image_pil.convert("RGB")

    def get_pipe_kwargs(self) -> dict:
        control_image_pil = self.get_control_image_pil()
        controlnet_conditioning_scale = float(self._node.get_parameter_value("controlnet_conditioning_scale"))
        control_guidance_end = float(self._node.get_parameter_value("control_guidance_end"))
        control_mode_int = self._control_mode_by_name[self._node.get_parameter_value("control_mode")]

        return {
            "control_image": control_image_pil,
            "controlnet_conditioning_scale": controlnet_conditioning_scale,
            "control_guidance_end": control_guidance_end,
            "control_mode": control_mode_int,
        }
