import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class ControlnetHunyuanditPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "Tencent-Hunyuan/HunyuanDiT-Diffusers",
            ],
        )
        self._controlnet_repo_parameter = HuggingFaceRepoParameter(
            node,
            parameter_name="controlnet_repo",
            repo_ids=[
                "Tencent-Hunyuan/HunyuanDiT-v1.2-ControlNet-Diffusers-Canny",
                "Tencent-Hunyuan/HunyuanDiT-v1.2-ControlNet-Diffusers-Depth",
                "Tencent-Hunyuan/HunyuanDiT-v1.2-ControlNet-Diffusers-Pose",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._controlnet_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Control image for ControlNet",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=25,
                input_types=["int"],
                type="int",
                tooltip="num_inference_steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=5.0,
                input_types=["float"],
                type="float",
                tooltip="guidance_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="controlnet_conditioning_scale",
                default_value=1.0,
                input_types=["float"],
                type="float",
                tooltip="controlnet_conditioning_scale",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        controlnet_errors = self._controlnet_repo_parameter.validate_before_node_run()
        if controlnet_errors:
            errors = (errors or []) + controlnet_errors
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_controlnet_repo_revision(self) -> tuple[str, str]:
        return self._controlnet_repo_parameter.get_repo_revision()

    def publish_output_image_preview_placeholder(self) -> None:
        width = self.get_width()
        height = self.get_height()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_control_image(self) -> Image:
        from pillow_nodes_library.utils import image_artifact_to_pil  # type: ignore[reportMissingImports]

        image_artifact = self._node.get_parameter_value("image")
        return image_artifact_to_pil(image_artifact)

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_controlnet_conditioning_scale(self) -> float:
        return float(self._node.get_parameter_value("controlnet_conditioning_scale"))

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "control_image": self.get_control_image(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "controlnet_conditioning_scale": self.get_controlnet_conditioning_scale(),
            "generator": self._seed_parameter.get_generator(),
        }

    def latents_to_image_pil(self, pipe: diffusers.HunyuanDiTControlNetPipeline, latents: Any) -> Image:
        latents = latents / pipe.vae.config.scaling_factor
        image = pipe.vae.decode(latents, return_dict=False)[0]
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image_preview_latents(self, pipe: diffusers.HunyuanDiTControlNetPipeline, latents: Any) -> None:
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.parameter_output_values["output_image"] = image_artifact
