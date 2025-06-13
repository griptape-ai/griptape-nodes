import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusionGligenPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "masterful/gligen-1-4-generation-text-box",
                "masterful/gligen-1-4-inpainting-text-box",
                "anhnct/Gligen_Text_Image",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="The prompt to guide image generation",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                tooltip="The prompt to not guide the image generation",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="gligen_phrases",
                input_types=["list"],
                type="list",
                tooltip="List of phrases describing objects to ground in the image",
                default_value=[],
            )
        )
        self._node.add_parameter(
            Parameter(
                name="gligen_boxes",
                input_types=["list"],
                type="list",
                tooltip="List of bounding boxes [xmin, ymin, xmax, ymax] (normalized 0-1) for each phrase",
                default_value=[],
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                tooltip="Height of generated image",
                default_value=512,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                tooltip="Width of generated image",
                default_value=512,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                tooltip="The number of denoising steps",
                default_value=50,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for generation",
                default_value=7.5,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="gligen_scheduled_sampling_beta",
                input_types=["float"],
                type="float",
                tooltip="Beta value for GLIGEN scheduled sampling (0.0 to 1.0)",
                default_value=1.0,
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                input_types=[],
                type="image",
                tooltip="Generated image with grounded objects",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        errors.extend(self._huggingface_repo_parameter.validate_before_node_run() or [])

        # Validate that gligen_phrases and gligen_boxes have the same length
        phrases = self.get_gligen_phrases()
        boxes = self.get_gligen_boxes()
        if len(phrases) != len(boxes):
            errors.append(
                ValueError(
                    f"Number of gligen_phrases ({len(phrases)}) must match number of gligen_boxes ({len(boxes)})"
                )
            )

        # Validate bounding box format
        for i, box in enumerate(boxes):
            if not isinstance(box, list) or len(box) != 4:  # noqa: PLR2004
                errors.append(ValueError(f"Bounding box {i} must be a list of 4 numbers [xmin, ymin, xmax, ymax]"))
            else:
                for j, coord in enumerate(box):
                    if not isinstance(coord, (int, float)) or coord < 0 or coord > 1:
                        errors.append(
                            ValueError(f"Bounding box {i} coordinate {j} must be a number between 0 and 1, got {coord}")
                        )
                if len(box) == 4 and box[0] >= box[2]:  # xmin >= xmax  # noqa: PLR2004
                    errors.append(ValueError(f"Bounding box {i}: xmin ({box[0]}) must be less than xmax ({box[2]})"))
                if len(box) == 4 and box[1] >= box[3]:  # ymin >= ymax  # noqa: PLR2004
                    errors.append(ValueError(f"Bounding box {i}: ymin ({box[1]}) must be less than ymax ({box[3]})"))

        return errors or None

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str | None:
        negative_prompt = self._node.get_parameter_value("negative_prompt")
        return negative_prompt if negative_prompt else None

    def get_gligen_phrases(self) -> list[str]:
        return self._node.get_parameter_value("gligen_phrases")

    def get_gligen_boxes(self) -> list[list[float]]:
        return self._node.get_parameter_value("gligen_boxes")

    def get_height(self) -> int:
        return self._node.get_parameter_value("height")

    def get_width(self) -> int:
        return self._node.get_parameter_value("width")

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_guidance_scale(self) -> float:
        return self._node.get_parameter_value("guidance_scale")

    def get_gligen_scheduled_sampling_beta(self) -> float:
        return self._node.get_parameter_value("gligen_scheduled_sampling_beta")

    def get_generator(self) -> torch.Generator:
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self.get_prompt(),
            "gligen_phrases": self.get_gligen_phrases(),
            "gligen_boxes": self.get_gligen_boxes(),
            "height": self.get_height(),
            "width": self.get_width(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "gligen_scheduled_sampling_beta": self.get_gligen_scheduled_sampling_beta(),
            "generator": self.get_generator(),
        }

        negative_prompt = self.get_negative_prompt()
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        placeholder_image = PIL.Image.new("RGB", (self.get_width(), self.get_height()), (128, 128, 128))
        placeholder_artifact = pil_to_image_artifact(placeholder_image)
        self._node.set_parameter_value("output_image", placeholder_artifact)

    def publish_output_image_preview_latents(self, pipe: diffusers.StableDiffusionGLIGENPipeline, latents: Any) -> None:
        try:
            with pipe.vae.disable_tiling():
                latents_scaled = 1 / pipe.vae.config.scaling_factor * latents
                image = pipe.vae.decode(latents_scaled, return_dict=False)[0]
                image = pipe.image_processor.postprocess(image, output_type="pil")[0]
                image_artifact = pil_to_image_artifact(image)
                self._node.set_parameter_value("output_image", image_artifact)
        except Exception as e:
            logger.warning("Failed to publish preview from latents: %s", e)

    def publish_output_image(self, image: Image) -> None:
        image_artifact = pil_to_image_artifact(image)
        self._node.set_parameter_value("output_image", image_artifact)
