import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.allegro.allegro_memory_footprint import (
    optimize_allegro_pipeline_memory_footprint,
)
from diffusers_nodes_library.pipelines.allegro.allegro_pipeline_parameters import (
    AllegroPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AllegroPipeline(ControlNode):
    fps = 15

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "image"
        self.description = self.__class__.__name__
        self.pipe_params = AllegroPipelineParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()


    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "output_format":
            modified_parameters_set.update(self.pipe_params.set_output_format(value))
            return

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.pipe_params.publish_output_preview_placeholder()

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo_id, revision = self.pipe_params.get_repo_revision()
            vae = model_cache.from_pretrained(
                diffusers.AutoencoderKLAllegro,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                subfolder="vae",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

            pipe = model_cache.from_pretrained(
                diffusers.AllegroPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
                vae=vae,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            # Without vae tiling --  NotImplementedError: "Decoding without tiling has not been implemented yet"
            pipe.enable_vae_tiling()
            optimize_allegro_pipeline_memory_footprint(pipe)

        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback_on_step_end(
            pipe: diffusers.FluxPipeline,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            if i < num_inference_steps - 1:
                self.pipe_params.publish_output_preview(pipe, callback_kwargs["latents"], fps=self.fps)
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

        self.pipe_params.publish_output_video(video_mystery_format, fps=self.fps)

        self.log_params.append_to_logs("Done.\n")
