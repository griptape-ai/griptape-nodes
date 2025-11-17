import logging
import math
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]
from utils.directory_utils import check_cleanup_intermediates_directory, get_intermediates_directory_path

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter

logger = logging.getLogger("diffusers_nodes_library")


DEFAULT_NUM_INFERENCE_STEPS = 20


class DiffusionPipelineRuntimeParameters(ABC):
    def __init__(self, node: BaseNode):
        self._node = node
        self._seed_parameter = SeedParameter(node)

    @abstractmethod
    def _add_input_parameters(self) -> None:
        raise NotImplementedError

    def add_input_parameters(self) -> None:
        self._add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=1024,
                type="int",
                tooltip="The width in pixels of the generated image.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=1024,
                type="int",
                tooltip="The height in pixels of the generated image.",
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

    @abstractmethod
    def _remove_input_parameters(self) -> None:
        raise NotImplementedError

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("width")
        self._node.remove_parameter_element_by_name("height")
        self._node.remove_parameter_element_by_name("num_inference_steps")
        self._seed_parameter.remove_input_parameters()
        self._remove_input_parameters()

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("output_image")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def process_pipeline(self, pipe: DiffusionPipeline) -> None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        num_inference_steps = self.get_num_inference_steps()
        # Default to False for better performance - preview intermediates slow down inference
        enable_preview = GriptapeNodes.ConfigManager().get_config_value(
            "advanced_media_library.enable_image_preview_intermediates", default=False
        )

        strength_affected_steps = math.ceil(num_inference_steps * (self._node.get_parameter_value("strength") or 1))

        first_iteration_time = None

        def callback_on_step_end(
            pipe: DiffusionPipeline,
            i: int,
            _t: int,
            callback_kwargs: dict,
        ) -> dict:
            nonlocal first_iteration_time
            # Check for cancellation request
            if self._node.is_cancellation_requested:
                pipe._interrupt = True
                self._node.log_params.append_to_logs("Cancellation requested, stopping after this step...\n")  # type: ignore[reportAttributeAccessIssue]
                return callback_kwargs

            if first_iteration_time is None:
                first_iteration_time = datetime.now(tz=UTC)
            if i < num_inference_steps - 1 and enable_preview:
                self.publish_output_image_preview_latents(pipe, callback_kwargs["latents"])
            if i == 0:
                self._node.log_params.append_to_logs(f"Completed inference step 1 of {strength_affected_steps}.\n")  # type: ignore[reportAttributeAccessIssue]
                self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
            else:
                self._node.log_params.append_to_logs(  # type: ignore[reportAttributeAccessIssue]
                    f"Completed inference step {i + 1} of {strength_affected_steps}. {f'{(datetime.now(tz=UTC) - first_iteration_time).total_seconds() / i:.2f}'} s/it\n"
                )
                self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
            return {}

        self._node.progress_bar_component.initialize(num_inference_steps)  # type: ignore[reportAttributeAccessIssue]

        output_image_pil = pipe(  # type: ignore[reportCallIssue]
            **self.get_pipe_kwargs(),
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).images[0]
        self.publish_output_image(output_image_pil)
        self._node.log_params.append_to_logs("Done.\n")  # type: ignore[reportAttributeAccessIssue]

    def publish_output_image_preview_placeholder(self) -> None:
        width = int(self.get_width())
        height = int(self.get_height())
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.

        # Check to ensure there's enough space in the intermediates directory
        # if that setting is enabled.
        check_cleanup_intermediates_directory()

        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter(
            "output_image",
            pil_to_image_artifact(preview_placeholder_image, directory_path=get_intermediates_directory_path()),
        )

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    @abstractmethod
    def _get_pipe_kwargs(self) -> dict:
        raise NotImplementedError

    def get_pipe_kwargs(self) -> dict:
        return {
            **self._get_pipe_kwargs(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": torch.Generator().manual_seed(self._seed_parameter.get_seed()),
        }

    def latents_to_image_pil(self, pipe: DiffusionPipeline, latents: Any) -> Image:
        width = int(self._node.parameter_values["width"])
        height = int(self._node.parameter_values["height"])
        latents = pipe._unpack_latents(latents, height, width, pipe.vae_scale_factor)
        latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
        image = pipe.vae.decode(latents, return_dict=False)[0]
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/845
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image_preview_latents(self, pipe: DiffusionPipeline, latents: Any) -> None:
        # Check to ensure there's enough space in the intermediates directory
        # if that setting is enabled.
        check_cleanup_intermediates_directory()

        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(
            preview_image_pil, directory_path=get_intermediates_directory_path()
        )
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.publish_update_to_parameter("output_image", image_artifact)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact

    def validate_before_node_run(self) -> list[Exception] | None:
        return None
