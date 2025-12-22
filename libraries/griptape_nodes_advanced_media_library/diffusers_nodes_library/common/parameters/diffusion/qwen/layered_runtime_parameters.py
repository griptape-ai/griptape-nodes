import logging
from typing import Any

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)
from utils.directory_utils import check_cleanup_intermediates_directory, get_intermediates_directory_path
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.parameters.diffusion.qwen.common import qwen_latents_to_image_pil
from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DEFAULT_NUM_INFERENCE_STEPS,
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")

DEFAULT_RESOLUTION = 640
RESOLUTION_OPTIONS = [DEFAULT_RESOLUTION, 1024]


class QwenLayeredPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input RGBA image to decompose into layers.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="The prompt or prompts to guide the image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value=" ",
                type="str",
                tooltip="The prompt or prompts not to guide the image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="true_cfg_scale",
                default_value=4.0,
                type="float",
                tooltip="True classifier-free guidance scale.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="layers",
                default_value=4,
                type="int",
                tooltip="Number of image layers to generate.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="resolution",
                default_value=DEFAULT_RESOLUTION,
                type="int",
                traits={Options(choices=RESOLUTION_OPTIONS)},
                tooltip=f"Resolution bucket. {DEFAULT_RESOLUTION} is recommended for this version.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=DEFAULT_NUM_INFERENCE_STEPS,
                type="int",
                tooltip="The number of denoising steps. More denoising steps usually lead to a higher quality image at the expense of slower inference.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="cfg_normalize",
                default_value=True,
                type="bool",
                tooltip="Whether to enable cfg normalization.",
                hide=True,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="use_en_prompt",
                default_value=True,
                type="bool",
                tooltip="Automatic caption language if user does not provide caption.",
                hide=True,
            )
        )

    def add_input_parameters(self) -> None:
        self._add_input_parameters()
        self._seed_parameter.add_input_parameters()

    def remove_input_parameters(self) -> None:
        self._seed_parameter.remove_input_parameters()
        self._remove_input_parameters()

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("image")
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("true_cfg_scale")
        self._node.remove_parameter_element_by_name("layers")
        self._node.remove_parameter_element_by_name("resolution")
        self._node.remove_parameter_element_by_name("num_inference_steps")
        self._node.remove_parameter_element_by_name("cfg_normalize")
        self._node.remove_parameter_element_by_name("use_en_prompt")

    def get_image_pil(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("image")
        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        return input_image_pil.convert("RGBA")

    def get_width(self) -> int:
        return self.get_image_pil().width

    def get_height(self) -> int:
        return self.get_image_pil().height

    def _get_pipe_kwargs(self) -> dict:
        return {
            "image": self.get_image_pil(),
            "prompt": self._node.get_parameter_value("prompt") or None,
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "true_cfg_scale": self._node.get_parameter_value("true_cfg_scale"),
            "layers": self._node.get_parameter_value("layers"),
            "resolution": self._node.get_parameter_value("resolution"),
            "cfg_normalize": self._node.get_parameter_value("cfg_normalize"),
            "use_en_prompt": self._node.get_parameter_value("use_en_prompt"),
        }

    def get_pipe_kwargs(self) -> dict:
        return {
            **self._get_pipe_kwargs(),
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": torch.Generator().manual_seed(self._seed_parameter.get_seed()),
        }

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image_list",
                output_type="list[ImageArtifact]",
                tooltip="The output images",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("output_image_list")

    def publish_output_image_preview_placeholder(self) -> None:
        width = int(self.get_width())
        height = int(self.get_height())
        check_cleanup_intermediates_directory()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter(
            "output_image_list",
            [pil_to_image_artifact(preview_placeholder_image, directory_path=get_intermediates_directory_path())],
        )

    def publish_output_image_list(self, output_images_pil: list[Image]) -> None:
        image_artifacts = [pil_to_image_artifact(img) for img in output_images_pil]
        self._node.publish_update_to_parameter("output_image_list", image_artifacts)
        self._node.set_parameter_value("output_image_list", image_artifacts)
        self._node.parameter_output_values["output_image_list"] = image_artifacts

    def _process_pipeline_output(self, pipe: DiffusionPipeline, callback_on_step_end: Any) -> None:
        output_images_pil = pipe(  # type: ignore[reportCallIssue]
            **self.get_pipe_kwargs(),
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).images[0]
        self.publish_output_image_list(output_images_pil)

    def latents_to_image_pil(self, pipe: DiffusionPipeline, latents: Any) -> Image:
        return qwen_latents_to_image_pil(pipe, latents, self.get_height(), self.get_width())
