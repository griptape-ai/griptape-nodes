import logging
import tempfile
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.pia.pia_pipeline_parameters import (
    PiaPipelineParameters,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.pia.pia_pipeline_memory_footprint import (
    optimize_pia_pipeline_memory_footprint,
)  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class PiaPipeline(ControlNode):
    """Griptape wrapper around diffusers.pipelines.pia.PIAPipeline."""
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = PiaPipelineParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        pass

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
        self.pipe_params.publish_output_video_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")

        with self.log_params.append_profile_to_logs("Loading motion adapter"):
            motion_adapter_repo_id = self.pipe_params.get_motion_adapter_repo_id()
            motion_adapter = model_cache.from_pretrained(
                diffusers.MotionAdapter,
                pretrained_model_name_or_path=motion_adapter_repo_id,
                torch_dtype=torch.float16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.PIAPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                motion_adapter=motion_adapter,
                torch_dtype=torch.float16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            optimize_pia_pipeline_memory_footprint(pipe)

        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback_on_step_end(
            pipe: diffusers.PIAPipeline,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            if i < num_inference_steps - 1:
                self.pipe_params.publish_output_video_preview_latents(pipe, callback_kwargs["latents"])
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            callback_on_step_end=callback_on_step_end,
        )

        # Save frames as video
        frames = output.frames[0]
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".gif") as temp_file:
            temp_path = temp_file.name
            
        # Export frames to GIF using diffusers utility
        from diffusers.utils import export_to_gif  # type: ignore[reportMissingImports]
        export_to_gif(frames, temp_path)
        
        self.pipe_params.publish_output_video(temp_path)
        self.log_params.append_to_logs("Done.\n")