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





class AllegroPipelineParameters:
    def __init__(self, node: ControlNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(node, ["rhymes-ai/Allegro"])
    
         
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
                name="num_inference_steps",
                default_value=100,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_inference_steps",
            )
        )
        # TODO: timesteps: List[int] = None,
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.5,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="guidance_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=88,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_frames",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=None,
                input_types=["int", "None"],
                # type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=None,
                input_types=["int", "None"],
                # type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="width",
            )
        )
        # num_videos_per_prompt: int = 1,
        # Skipping for now
        # eta: float = 0.0,
        self._node.add_parameter(
            Parameter(
                name="eta",
                default_value=0.0,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="eta",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="seed",
                default_value=None,
                input_types=["int", "None"],
                # type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="seed",
            )
        )
        
        # output_type: Optional[str] = "pil",
        # return_dict: bool = True,
        # callback_on_step_end: Optional[
        #     Union[Callable[[int, int, Dict], None], PipelineCallback, MultiPipelineCallbacks]
        # ] = None,
        # callback_on_step_end_tensor_inputs: List[str] = ["latents"],
        # clean_caption: bool = True,
        # max_sequence_length: int = 512,
        

    def add_output_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact", # Hint for UI
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="URL of the extended video segment.",
                ui_options={"placeholder_text": "", "is_full_width": True} 
            )
        )

    def get_repo_revision(self):
        return self._huggingface_repo_parameter.get_repo_revision()
    
        
    def get_num_inference_steps(self):
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict:
        prompt = self._node.parameter_values["prompt"]
        negative_prompt = self._node.parameter_values["negative_prompt"]
        width = self._node.get_parameter_value("width")
        if width is not None:
            width = int(width)
        height = self._node.get_parameter_value("height")
        if height is not None:
            height = int(height)
        num_inference_steps = int(self._node.parameter_values["num_inference_steps"])
        guidance_scale = float(self._node.parameter_values["guidance_scale"])
        num_frames = int(self._node.parameter_values["num_frames"])
        eta = float(self._node.parameter_values["eta"])
        seed = self._node.get_parameter_value("seed")
        generator = torch.Generator("cpu")
        if seed is not None:
            generator = generator.manual_seed(seed)

        return {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "num_frames": num_frames,
            "eta": eta,
            "generator": generator,
        }
    
    # def latents_to_image_pil(self, pipe: diffusers.FluxPipeline | diffusers.FluxControlNetPipeline, latents: Any) -> Image:
    #     width = int(self._node.parameter_values["width"])
    #     height = int(self._node.parameter_values["height"])
    #     latents = pipe._unpack_latents(latents, height, width, pipe.vae_scale_factor)
    #     latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
    #     image = pipe.vae.decode(latents, return_dict=False)[0]
    #     # TODO: https://github.com/griptape-ai/griptape-nodes/issues/845
    #     intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
    #     return intermediate_pil_image
    

    # def publish_output_image_preview_latents(self, pipe: diffusers.FluxPipeline | diffusers.FluxControlNetPipeline, latents: Any):
    #     preview_image_pil = self.latents_to_image_pil(pipe, latents)
    #     preview_image_artifact = pil_to_image_artifact(preview_image_pil)
    #     self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    # def publish_output_image(self, output_image_pil: Image):
    #     image_artifact = pil_to_image_artifact(output_image_pil)
    #     self._node.set_parameter_value("output_image", image_artifact)
    #     self._node.parameter_output_values["output_image"] = image_artifact


    def publish_output_image_preview_placeholder(self):
        width = int(self._node.parameter_values["width"])
        height = int(self._node.parameter_values["height"])
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def publish_output_video(self, video_mystery_format: Any, fps):
        video_path = Path(diffusers.utils.export_to_video(video_mystery_format, fps=15))
        video_bytes = open(video_path, "rb").read()
        video_filename = f"{uuid.uuid4()}{video_path.suffix}"
        video_url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, video_filename)
        video_artifact = VideoUrlArtifact(url=video_url, name=video_filename)
        
        self._node.set_parameter_value("output_video", video_artifact)
        self._node.parameter_output_values["output_video"] = video_artifact
