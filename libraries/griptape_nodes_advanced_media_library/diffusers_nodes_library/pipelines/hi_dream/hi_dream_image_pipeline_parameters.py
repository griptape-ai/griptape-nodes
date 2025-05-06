import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class HiDreamImagePipelineParameters:
    def __init__(self, node: ControlNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "HiDream-ai/HiDream-I1-Fast",
                "HiDream-ai/HiDream-I1-Full",
                "HiDream-ai/HiDream-I1-Dev",
            ],
        )

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt_2",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional - defaults to prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt_3",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional - defaults to prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt_4",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional - defaults to prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=1024,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=1024,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=50,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_inference_steps",
            )
        )
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/841
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=3.5,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="guidance_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt_2",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional - defaults to negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt_3",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional - defaults to negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt_4",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional - defaults to negative_prompt",
            )
        )
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/842
        self._node.add_parameter(
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional - random seed, default is random seed",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="true_cfg_scale",
                default_value=1.0,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="true_cfg_scale",
            )
        )

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def publish_output_image_preview_placeholder(self) -> None:
        width = int(self._node.parameter_values["width"])
        height = int(self._node.parameter_values["height"])
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def get_pipe_kwargs(self) -> dict:
        prompt = self._node.parameter_values["prompt"]
        prompt_2 = self._node.parameter_values.get("prompt_2", prompt)
        prompt_3 = self._node.parameter_values.get("prompt_3", prompt)
        prompt_4 = self._node.parameter_values.get("prompt_4", prompt)
        height = int(self._node.parameter_values["height"])
        width = int(self._node.parameter_values["width"])
        num_inference_steps = int(self._node.parameter_values["num_inference_steps"])
        guidance_scale = float(self._node.parameter_values["guidance_scale"])
        negative_prompt = self._node.parameter_values["negative_prompt"]
        negative_prompt_2 = self._node.parameter_values.get("negative_prompt_2", negative_prompt)
        negative_prompt_3 = self._node.parameter_values.get("negative_prompt_3", negative_prompt)
        negative_prompt_4 = self._node.parameter_values.get("negative_prompt_4", negative_prompt)
        seed = int(self._node.parameter_values["seed"]) if ("seed" in self._node.parameter_values) else None

        generator = torch.Generator("cpu")
        if seed is not None:
            generator = generator.manual_seed(seed)

        return {
            "prompt": prompt,
            "prompt_2": prompt_2,
            "prompt_3": prompt_3,
            "prompt_4": prompt_4,
            "height": height,
            "width": width,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "negative_prompt": negative_prompt,
            "negative_prompt_2": negative_prompt_2,
            "negative_prompt_3": negative_prompt_3,
            "negative_prompt_4": negative_prompt_4,
            "generator": generator,
        }

    def latents_to_image_pil(
        self, pipe: diffusers.FluxPipeline | diffusers.FluxControlNetPipeline, latents: Any
    ) -> Image:
        latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
        image = pipe.vae.decode(latents, return_dict=False)[0]
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/845
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image_preview_latents(
        self, pipe: diffusers.FluxPipeline | diffusers.FluxControlNetPipeline, latents: Any
    ) -> None:
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))
