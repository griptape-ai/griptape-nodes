import logging
from typing import Any

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class Cosmos2TextToImagePipelineParameters:
    """Wrapper around the collection of parameters needed for Cosmos2 text-to-image pipelines."""

    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "nvidia/Cosmos-Predict2-2B-Text2Image",
                "nvidia/Cosmos-Predict2-14B-Text2Image",
            ],
        )
        self._huggingface_guardrail_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "meta-llama/LlamaGuard-7b",
            ],
            parameter_name="guardrail_model",
        )
        self._seed_parameter = SeedParameter(node)

    # ---------------------------------------------------------------------
    # Parameter registration helpers
    # ---------------------------------------------------------------------
    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._huggingface_guardrail_repo_parameter.add_input_parameters()

        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Negative prompt (optional)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.0,
                input_types=["float"],
                type="float",
                tooltip="CFG / guidance scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=1360,
                input_types=["int"],
                type="int",
                tooltip="Width in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=768,
                input_types=["int"],
                type="int",
                tooltip="Height in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=35,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
            )
        )

        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="Generated image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # ------------------------------------------------------------------
    # Validation / life-cycle hooks
    # ------------------------------------------------------------------
    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run() or []
        errors += self._huggingface_guardrail_repo_parameter.validate_before_node_run() or []
        return errors

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    # ------------------------------------------------------------------
    # Convenience getters
    # ------------------------------------------------------------------
    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_generator(self) -> torch.Generator:
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "guidance_scale": self.get_guidance_scale(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": self.get_generator(),
        }

    # ------------------------------------------------------------------
    # Preview helpers
    # ------------------------------------------------------------------
    def publish_output_image_preview_placeholder(self) -> None:
        width = self.get_width()
        height = self.get_height()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def latents_to_image_pil(self, pipe: Any, latents: Any) -> Image:
        # Use the VAE to decode latents to image
        latents_mean = (
            torch.tensor(pipe.vae.config.latents_mean)
            .view(1, pipe.vae.config.z_dim, 1, 1, 1)
            .to(latents.device, latents.dtype)
        )
        latents_std = 1.0 / torch.tensor(pipe.vae.config.latents_std).view(1, pipe.vae.config.z_dim, 1, 1, 1).to(
            latents.device, latents.dtype
        )
        latents = latents / latents_std / pipe.scheduler.config.sigma_data + latents_mean
        video = pipe.vae.decode(latents.to(pipe.vae.dtype), return_dict=False)[0]

        video = pipe.video_processor.postprocess_video(video, output_type="pil")
        images = [batch[0] for batch in video]
        return images[0]

    def publish_output_image_preview_latents(self, pipe: Any, latents: Any) -> None:
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
