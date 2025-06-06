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
from diffusers_nodes_library.pipelines.ltx.ltx_pipeline_parameters import (
    LtxPipelineParameters,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.ltx.ltx_pipeline_memory_footprint import (
    optimize_ltx_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
    print_ltx_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class LtxPipeline(ControlNode):
    """Griptape wrapper around diffusers.LTXVideoPipeline."""

    def __init__(self, **kwargs) -> None:  # noqa: D401
        super().__init__(**kwargs)
        self.pipe_params = LtxPipelineParameters(self)
        self.log_params = LogParameter(self)

        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def after_value_set(
        self, parameter: Parameter, value: Any, modified_parameters_set: set[str]
    ) -> None:
        self.pipe_params.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:  # noqa: D401
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def process(self) -> AsyncResult | None:  # noqa: D401
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:  # noqa: C901
        self.preprocess()
        self.pipe_params.publish_output_video_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")

        # -------------------------------------------------------------
        # Model loading
        # -------------------------------------------------------------
        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo_id, revision = self.pipe_params.get_repo_revision()
            pipe: diffusers.LTXVideoPipeline = model_cache.from_pretrained(
                diffusers.LTXVideoPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype=torch.float16,
                local_files_only=True,
            )

        with (
            self.log_params.append_profile_to_logs("Loading model"),
            self.log_params.append_logs_to_logs(logger),
        ):
            optimize_ltx_pipeline_memory_footprint(pipe)

        # -------------------------------------------------------------
        # Inference
        # -------------------------------------------------------------
        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback_on_step_end(
            step: int,
            _timestep: int,
            callback_kwargs: dict,
        ) -> dict:  # noqa: D401
            if step < num_inference_steps - 1:
                self.log_params.append_to_logs(
                    f"Starting inference step {step + 2} of {num_inference_steps}...\n"
                )
            return {}

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_video = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            output_type="np",
            callback_on_step_end=callback_on_step_end,
        ).frames[0]

        self.pipe_params.publish_output_video(output_video)
        self.log_params.append_to_logs("Done.\n")

        # Optionally dump a final memory report
        logger.info("LTX Video memory footprint after inference:")
        print_ltx_pipeline_memory_footprint(pipe)