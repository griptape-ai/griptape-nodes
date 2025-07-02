import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class FluxKontextPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "black-forest-labs/FLUX.1-Kontext-dev",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="text_encoder",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="text_encoder",
                default_value="openai/clip-vit-large-patch14",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="text_encoder_2",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="text_encoder_2",
                default_value="google/t5-v1_1-xxl",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image for img2img generation (optional)",
            )
        )
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
                name="prompt_2",
                input_types=["str"],
                type="str",
                tooltip="optional prompt_2 - defaults to prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="optional negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt_2",
                input_types=["str"],
                type="str",
                tooltip="optional negative_prompt_2 - defaults to negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="true_cfg_scale",
                default_value=1.0,
                input_types=["float"],
                type="float",
                tooltip="true_cfg_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width_by_height",
                default_value="1024x1024",
                input_types=["str"],
                type="str",
                tooltip="widthxheight",
                traits={
                    Options(
                        choices=[
                            "688x1504",
                            "720x1456",
                            "752x1392",
                            "800x1328",
                            "832x1248",
                            "880x1184",
                            "944x1104",
                            "1024x1024",
                            "1104x944",
                            "1184x880",
                            "1248x832",
                            "1328x800",
                            "1392x752",
                            "1456x720",
                            "1504x688",
                        ]
                    )
                },
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=28,
                input_types=["int"],
                type="int",
                tooltip="num_inference_steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=3.5,
                input_types=["float"],
                type="float",
                tooltip="guidance_scale",
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
        errors = self._huggingface_repo_parameter.validate_before_node_run() or []
        # Check for if prompt exists:
        prompt_exists = self.get_prompt() or self.get_prompt_2()
        negative_prompt_exists = self.get_negative_prompt() or self.get_negative_prompt_2()
        image_exists = self.get_input_image_pil()
        if not prompt_exists and not negative_prompt_exists and not image_exists:
            errors.append(ValueError("At least one prompt, negative prompt, or image must be provided."))

        # Validate dimensions based on diffusers source logic
        width = self.get_width()
        height = self.get_height()

        if width * height > (1024 * 1024):
            errors.append(ValueError(f"Width ({width}) * Height ({height}) must be less than 1024*1024"))

        # Get actual VAE scale factor from model config
        try:
            repo_id, revision = self.get_repo_revision()
            vae_config = diffusers.AutoencoderKLConfig.from_pretrained(
                pretrained_model_name_or_path=repo_id, revision=revision, local_files_only=True, subfolder="vae"
            )
            vae_scale_factor = 2 ** (len(vae_config.block_out_channels) - 1)
            # Flux latents are packed into 2x2 patches, so multiply by 2
            multiple_of = vae_scale_factor * 2
        except Exception:
            # Fallback to standard Flux values if model loading fails
            multiple_of = 16

        if width % multiple_of != 0:
            errors.append(ValueError(f"Width ({width}) must be divisible by {multiple_of}"))

        if height % multiple_of != 0:
            errors.append(ValueError(f"Height ({height}) must be divisible by {multiple_of}"))

        if width <= 0:
            errors.append(ValueError(f"Width must be positive, got {width}"))

        if height <= 0:
            errors.append(ValueError(f"Height must be positive, got {height}"))

        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_input_image_pil(self) -> Image | None:
        image_artifact = self._node.get_parameter_value("image")
        if image_artifact is None:
            return None
        if isinstance(image_artifact, ImageUrlArtifact):
            image_artifact = load_image_from_url_artifact(image_artifact)
        input_image_pil = image_artifact_to_pil(image_artifact)
        return input_image_pil.convert("RGB")

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_prompt_2(self) -> str:
        prompt_2 = self._node.get_parameter_value("prompt_2")
        if prompt_2 is None:
            return self.get_prompt()
        return prompt_2

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_negative_prompt_2(self) -> str:
        negative_prompt_2 = self._node.get_parameter_value("negative_prompt_2")
        if negative_prompt_2 is None:
            return self.get_negative_prompt()
        return negative_prompt_2

    def get_true_cfg_scale(self) -> float:
        return float(self._node.get_parameter_value("true_cfg_scale"))

    def get_width(self) -> int:
        width_by_height = self._node.get_parameter_value("width_by_height")
        return int(width_by_height.split("x")[0])

    def get_height(self) -> int:
        width_by_height = self._node.get_parameter_value("width_by_height")
        return int(width_by_height.split("x")[1])

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_effective_size(self) -> tuple[int, int]:
        """Get the effective width and height."""
        return self.get_width(), self.get_height()

    def get_pipe_kwargs(self) -> dict:
        return {
            "image": self.get_input_image_pil(),
            "prompt": self.get_prompt(),
            "prompt_2": self.get_prompt_2(),
            "negative_prompt": self.get_negative_prompt(),
            "negative_prompt_2": self.get_negative_prompt_2(),
            "true_cfg_scale": self.get_true_cfg_scale(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_image_preview_placeholder(self) -> None:
        width, height = self.get_effective_size()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def latents_to_image_pil(self, pipe: diffusers.FluxKontextPipeline, latents: Any) -> Image:
        width, height = self.get_effective_size()
        latents = pipe._unpack_latents(latents, height, width, pipe.vae_scale_factor)
        latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
        image = pipe.vae.decode(latents, return_dict=False)[0]
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image_preview_latents(self, pipe: diffusers.FluxKontextPipeline, latents: Any) -> None:
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
