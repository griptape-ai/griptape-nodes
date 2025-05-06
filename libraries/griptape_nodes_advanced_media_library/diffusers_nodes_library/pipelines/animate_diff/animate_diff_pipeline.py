import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.animate_diff.animate_diff_memory_footprint import (
    optimize_animate_diff_pipeline_memory_footprint,
)
from diffusers_nodes_library.pipelines.animate_diff.animate_diff_pipeline_parameters import (
    AnimateDiffPipelineParameters,
)  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AnimateDiffPipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "video"
        self.description = self.__class__.__name__
        self.pipe_params = AnimateDiffPipelineParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.log_params.append_to_logs("Preparing models...\n")

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            motion_adapter_repo_id, motion_adapter_revision = self.pipe_params.get_motion_adapter_repo_revision()
            motion_adapter = model_cache.from_pretrained(
                diffusers.MotionAdapter,
                pretrained_model_name_or_path=motion_adapter_repo_id,
                revision=motion_adapter_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

            model_repo_id, model_revision = self.pipe_params.get_model_repo_revision()
            scheduler = model_cache.from_pretrained(
                diffusers.DDIMScheduler,
                pretrained_model_name_or_path=model_repo_id,
                revision=model_revision,
                subfolder="scheduler",
                clip_sample=False,
                timestep_spacing="linspace",
                beta_schedule="linear",
                steps_offset=1,
            )

            pipe = model_cache.from_pretrained(
                diffusers.AnimateDiffPipeline,
                pretrained_model_name_or_path=model_repo_id,
                revision=model_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
                motion_adapter=motion_adapter,
                scheduler=scheduler,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            optimize_animate_diff_pipeline_memory_footprint(pipe)

        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback_on_step_end(
            pipe: diffusers.FluxPipeline,  # noqa: ARG001
            i: int,
            _t: Any,
            callback_kwargs: dict,  # noqa: ARG001
        ) -> dict:
            if i < num_inference_steps - 1:
                # Publish output preview here
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        video_mystery_format = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            output_type="pil",
            # `clean_caption`
            #   Whether or not to clean the caption before creating embeddings. Requires `beautifulsoup4` and `ftfy` to
            #   be installed. If the dependencies are not installed, the embeddings will be created from the raw
            #   prompt.
            #
            #   Requires beautifulsoup4 to use, so disabling it for now.
            clean_caption=False,
            callback_on_step_end=callback_on_step_end,
        ).frames[0]

        self.pipe_params.publish_output_video(video_mystery_format, fps=15)

        self.log_params.append_to_logs("Done.\n")
