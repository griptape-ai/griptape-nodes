import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import (
    model_cache,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.i2vgen_xl.i2vgen_xl_pipeline_memory_footprint import (
    optimize_i2vgen_xl_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
    print_i2vgen_xl_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.i2vgen_xl.i2vgen_xl_pipeline_parameters import (
    I2VGenXLPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class I2VGenXLPipeline(ControlNode):
    """Griptape wrapper around diffusers.I2VGenXLPipeline."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = I2VGenXLPipelineParameters(self)
        self.log_params = LogParameter(self)

        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self.pipe_params.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
        self.log_params.append_to_logs("Preparing models...\n")

        # -------------------------------------------------------------
        # Model loading
        # -------------------------------------------------------------
        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo_id, revision = self.pipe_params.get_repo_revision()
            pipe: diffusers.I2VGenXLPipeline = model_cache.from_pretrained(
                diffusers.I2VGenXLPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype=torch.float16,
                local_files_only=True,
            )

        with (
            self.log_params.append_profile_to_logs("Loading model"),
            self.log_params.append_logs_to_logs(logger),
        ):
            optimize_i2vgen_xl_pipeline_memory_footprint(pipe)

        # -------------------------------------------------------------
        # Inference
        # -------------------------------------------------------------
        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback_on_step_end(
            step: int,
            _timestep: int,
            _callback_kwargs: dict,
        ) -> dict:
            if step < num_inference_steps - 1:
                self.log_params.append_to_logs(f"Starting inference step {step + 2} of {num_inference_steps}...\n")
            return {}

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        video_frames = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            output_type="pt",
            callback_on_step_end=callback_on_step_end,
        ).frames[0]

        self.pipe_params.publish_output_video(video_frames)
        self.log_params.append_to_logs("Done.\n")

        # Optionally dump a final memory report
        logger.info("I2VGen-XL memory footprint after inference:")
        print_i2vgen_xl_pipeline_memory_footprint(pipe)
