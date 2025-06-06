import logging
from pathlib import Path
import tempfile
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.cosmos.cosmos_pipeline_parameters import (  # type: ignore[reportMissingImports]
    CosmosPipelineParameters,
)
from diffusers_nodes_library.pipelines.cosmos.cosmos_pipeline_memory_footprint import (  # type: ignore[reportMissingImports]
    optimize_cosmos_pipeline_memory_footprint,
    print_cosmos_pipeline_memory_footprint,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class CosmosPipeline(ControlNode):
    """Griptape wrapper around diffusers.pipelines.cosmos.CosmosPipeline."""

    def __init__(self, **kwargs) -> None:  # noqa: D401,D403
        super().__init__(**kwargs)
        self.pipe_params = CosmosPipelineParameters(self)
        self.log_params = LogParameter(self)

        # Register parameters on the node.
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    # ------------------------------------------------------------------
    # Node lifecycle hooks
    # ------------------------------------------------------------------

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self.pipe_params.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:  # noqa: D401
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:  # noqa: D401
        self.pipe_params.preprocess()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def process(self) -> AsyncResult | None:  # noqa: D401
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:  # noqa: C901, D401
        self.preprocess()

        self.log_params.append_to_logs("Preparing models...\n")

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()

            # For now, create a placeholder implementation since CosmosPipeline may not be available yet
            # This will need to be updated when the actual pipeline is available in diffusers
            try:
                pipe = model_cache.from_pretrained(
                    diffusers.CosmosPipeline,
                    pretrained_model_name_or_path=base_repo_id,
                    revision=base_revision,
                    torch_dtype=torch.bfloat16,
                    local_files_only=True,
                )
            except AttributeError:
                # Fallback to a video pipeline until CosmosPipeline is available
                self.log_params.append_to_logs("CosmosPipeline not available, using placeholder...\n")
                return None

            # Print initial memory footprint.
            print_cosmos_pipeline_memory_footprint(pipe)

            # Optimise & move to device.
            optimize_cosmos_pipeline_memory_footprint(pipe)

        # ------------------------------------------------------------------
        # Inference
        # ------------------------------------------------------------------

        self.log_params.append_to_logs("Starting generation...\n")

        with (
            self.log_params.append_profile_to_logs("Generating video"),
            self.log_params.append_logs_to_logs(logger),
            self.log_params.append_stdout_to_logs(),
        ):
            frames = pipe(**self.pipe_params.get_pipe_kwargs()).frames[0]

        # ------------------------------------------------------------------
        # Export video & publish
        # ------------------------------------------------------------------

        with (
            self.log_params.append_profile_to_logs("Exporting video"),
            self.log_params.append_logs_to_logs(logger),
            self.log_params.append_stdout_to_logs(),
        ):
            temp_file = Path(tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name)
            try:
                diffusers.utils.export_to_video(frames, str(temp_file), fps=24)
                self.pipe_params.publish_output_video(temp_file)
            finally:
                if temp_file.exists():
                    temp_file.unlink()

        self.log_params.append_to_logs("Done.\n")