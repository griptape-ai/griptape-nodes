import logging
from pathlib import Path
import tempfile
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.wan.wan_loras_parameter import WanLorasParameter  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.wan.wan_pipeline_memory_footprint import (
    optimize_wan_pipeline_memory_footprint,
    print_wan_pipeline_memory_footprint,
)  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.wan.wan_pipeline_parameters import (
    WanPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode



logger = logging.getLogger("diffusers_nodes_library")


class WanPipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = WanPipelineParameters(self)
        self.loras_param = WanLorasParameter(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.loras_param.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self.pipe_params.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
        # self.pipe_params.publish_output_image_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")

        with self.log_params.append_profile_to_logs("Loading model metadata"), self.log_params.append_logs_to_logs(logger=logger):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()

            vae = model_cache.from_pretrained(
                diffusers.AutoencoderKLWan,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                subfolder="vae",
                # torch_dtype=torch.bfloat16,
                torch_dtype=torch.float32,
                local_files_only=True,
            )

            pipe = model_cache.from_pretrained(
                diffusers.WanPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
                vae=vae,
            )

            # flow_shift = 5.0  # 5.0 for 720P

            flow_shift = 3.0  # 3.0 for 480P

            pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=flow_shift)

            print_wan_pipeline_memory_footprint(pipe=pipe)

            logger.info("Moving to gpu")
            pipe.to("cuda")

        with (
            self.log_params.append_profile_to_logs("Configuring flux loras"),
            self.log_params.append_logs_to_logs(logger),
        ):
            self.loras_param.configure_loras(pipe)


        # with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
        #     optimize_wan_pipeline_memory_footprint(pipe)

        # num_inference_steps = self.pipe_params.get_num_inference_steps()

        # def callback_on_step_end(
        #     pipe: diffusers.WanPipeline,
        #     i: int,
        #     _t: Any,
        #     callback_kwargs: dict,
        # ) -> dict:
        #     if i < num_inference_steps - 1:
        #         self.pipe_params.publish_output_image_preview_latents(pipe, callback_kwargs["latents"])
        #         self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
        #     return {}

        # self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        # output_image_pil = pipe(
        #     **self.pipe_params.get_pipe_kwargs(),
        #     output_type="pil",
        #     callback_on_step_end=callback_on_step_end,
        # ).images[0]
        # self.pipe_params.publish_output_image(output_image_pil)
        # self.log_params.append_to_logs("Done.\n")

        with self.log_params.append_profile_to_logs("Generating video"), self.log_params.append_logs_to_logs(logger=logger), self.log_params.append_stdout_to_logs():
            frames = pipe(
                **self.pipe_params.get_pipe_kwargs(),
            ).frames[0]
        
        with self.log_params.append_profile_to_logs("Exporting to video"), self.log_params.append_logs_to_logs(logger=logger), self.log_params.append_stdout_to_logs():
            temp_file = Path(tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name)
            try:
                diffusers.utils.export_to_video(frames, str(temp_file), fps=16)
                self.pipe_params.publish_output_video(temp_file)
            finally:
                if temp_file.exists():
                    temp_file.unlink()

