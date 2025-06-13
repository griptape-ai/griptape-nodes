import logging
import tempfile
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
from diffusers.utils import export_to_video  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.animatediff.animatediff_pipeline_memory_footprint import (  # type: ignore[reportMissingImports]
    optimize_animatediff_pipeline_memory_footprint,
    print_animatediff_pipeline_memory_footprint,
)
from diffusers_nodes_library.pipelines.animatediff.animatediff_pipeline_parameters import (  # type: ignore[reportMissingImports]
    AnimateDiffPipelineParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AnimateDiffPipeline(ControlNode):
    """Griptape wrapper around diffusers.AnimateDiffPipeline (text-to-video)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = AnimateDiffPipelineParameters(self)
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
        return self.pipe_params.validate_before_node_run()

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

            # Load MotionAdapter first (it is relatively small).
            adapter = model_cache.from_pretrained(
                diffusers.MotionAdapter,  # type: ignore[attr-defined]
                pretrained_model_name_or_path="guoyww/animatediff-motion-adapter-v1-5-2",
                torch_dtype="auto",
                local_files_only=True,
            )

            # Now load the main AnimateDiff pipeline with base Stable-Diffusion model.
            pipe: diffusers.AnimateDiffPipeline = model_cache.from_pretrained(
                diffusers.AnimateDiffPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                motion_adapter=adapter,
                torch_dtype="auto",
                local_files_only=True,
            )

        with (
            self.log_params.append_profile_to_logs("Optimizing model"),
            self.log_params.append_logs_to_logs(logger),
        ):
            optimize_animatediff_pipeline_memory_footprint(pipe)

        # -------------------------------------------------------------
        # Inference
        # -------------------------------------------------------------
        num_inference_steps = self.pipe_params.get_num_inference_steps()
        self.log_params.append_to_logs(f"Starting inference ({num_inference_steps} steps)...\n")

        frames = pipe(**self.pipe_params.get_pipe_kwargs()).frames[0]

        # -------------------------------------------------------------
        # Export video and publish
        # -------------------------------------------------------------
        with self.log_params.append_profile_to_logs("Exporting video"), self.log_params.append_logs_to_logs(logger):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
                temp_file = Path(temp_file_obj.name)
            try:
                export_to_video(frames, str(temp_file), fps=8)
                self.pipe_params.publish_output_video(temp_file)
            finally:
                if temp_file.exists():
                    temp_file.unlink()

        self.log_params.append_to_logs("Done.\n")

        logger.info("AnimateDiff memory footprint after inference:")
        print_animatediff_pipeline_memory_footprint(pipe)
