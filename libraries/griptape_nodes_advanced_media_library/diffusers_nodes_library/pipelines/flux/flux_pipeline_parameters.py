import os
from pathlib import Path
import time
from typing import Any, Iterator, OrderedDict, Protocol, runtime_checkable

import contextlib
import logging
import uuid

from griptape.artifacts import ImageUrlArtifact, UrlArtifact
from griptape.loaders import ImageLoader
import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from PIL.Image import Image
from diffusers_nodes_library.utils.lora_utils import configure_flux_loras # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.parameter_utils import HuggingFaceRepoParameter, VideoUrlArtifact
import torch  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

from diffusers_nodes_library.utils.logging_utils import StdoutCapture, LoggerCapture  # type: ignore[reportMissingImports]

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options


from diffusers_nodes_library.utils.huggingface_utils import (  # type: ignore[reportMissingImports]
    list_repo_revisions_in_cache,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


class FluxPipelineParameters:
    def __init__(self, node: ControlNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "black-forest-labs/FLUX.1-schnell",
                "black-forest-labs/FLUX.1-dev",
            ]
        )
         
    def add_input_parameters(self):
        self._huggingface_repo_parameter.add_parameter()
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
                tooltip="optional prompt_2 - defaults to prompt",
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
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional negative_prompt_2 - defaults to negative_prompt",
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
                name="num_inference_steps",
                default_value=4,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_inference_steps",
            )
        )
        # self._node.add_parameter(
        #     Parameter(
        #         name="sigmas",
        #         input_types=["list[float]", "None"],
        #         type="list[float]",
        #         allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
        #         tooltip="sigmas",
        #     )
        # )
        self._node.add_parameter(
            Parameter(
                name="sigmas",
                input_types=["str", "list[float]", "None"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="sigmas",
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

    def add_output_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def get_repo_revision(self):
        return self._huggingface_repo_parameter.get_repo_revision()

    def publish_output_image_preview_placeholder(self):
        width = int(self._node.parameter_values["width"])
        height = int(self._node.parameter_values["height"])
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))


    def get_sigmas(self) -> list[float] | None:
        sigmas = self._node.get_parameter_value("sigmas")
        if isinstance(sigmas, str):
            return [float(sigma) for sigma in sigmas.split(",")]
        return sigmas


    def get_pipe_kwargs(self) -> dict:
        prompt = self._node.parameter_values["prompt"]
        prompt_2 = self._node.parameter_values.get("prompt_2", prompt)
        negative_prompt = self._node.parameter_values["negative_prompt"]
        negative_prompt_2 = self._node.parameter_values.get("negative_prompt_2", negative_prompt)
        true_cfg_scale = float(self._node.parameter_values["true_cfg_scale"])
        width = int(self._node.parameter_values["width"])
        height = int(self._node.parameter_values["height"])
        num_inference_steps = int(self._node.parameter_values["num_inference_steps"])
        guidance_scale = float(self._node.parameter_values["guidance_scale"])
        seed = int(self._node.parameter_values["seed"]) if ("seed" in self._node.parameter_values) else None

        generator = torch.Generator("cpu")
        if seed is not None:
            generator = generator.manual_seed(seed)

        sigmas = self.get_sigmas()
        num_inference_steps = num_inference_steps if sigmas is None else len(sigmas)


        # num_inference_steps = 4, sigmas = None -- (input)
        # sigmas: [1.   0.75 0.5  0.25]
        # mu: 1.15
        # timesteps: tensor([1000.,  750.,  500.,  250.], device='mps:0')

        # num_inference_steps = 4, sigmas = 1,0.75,0.5,0.25 -- (input)
        # sigmas: [1.   0.75 0.5  0.25]
        # mu: 1.15
        # timesteps: tensor([1000.,  750.,  500.,  250.], device='mps:0')

        # num_inference_steps = 4, sigmas = 1,0.9,0.3,0.15 -- (input)
        # sigmas: [1.0, 0.9, 0.3, 0.15]
        # mu: 1.15
        # timesteps: tensor([1000.,  900.,  300.,  150.], device='mps:0')

        # sigmas: [1.0, 0.9, 0.8, 0.7]
        # mu: 1.15
        # timesteps: tensor([1000.,  900.,  800.,  700.], device='mps:0')
        # num_inference_steps: 4




        return {
            "prompt": prompt,
            "prompt_2": prompt_2,
            "negative_prompt": negative_prompt,
            "negative_prompt_2": negative_prompt_2,
            "true_cfg_scale": true_cfg_scale,
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "sigmas": sigmas,
            "guidance_scale": guidance_scale,
            "generator": generator,
        }
    
    def latents_to_image_pil(self, pipe: diffusers.FluxPipeline | diffusers.FluxControlNetPipeline, latents: Any) -> Image:
        width = int(self._node.parameter_values["width"])
        height = int(self._node.parameter_values["height"])
        latents = pipe._unpack_latents(latents, height, width, pipe.vae_scale_factor)
        latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
        image = pipe.vae.decode(latents, return_dict=False)[0]
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/845
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image
    

    def publish_output_image_preview_latents(self, pipe: diffusers.FluxPipeline | diffusers.FluxControlNetPipeline, latents: Any):
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image):
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
    
    def get_num_inference_steps(self):
        return self._node.get_parameter_value("num_inference_steps")
