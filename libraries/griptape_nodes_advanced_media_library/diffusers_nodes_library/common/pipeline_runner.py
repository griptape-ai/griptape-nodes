import asyncio
import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter
from diffusers_nodes_library.common.parameters.pipeline_runner_parameters import PipelineRunnerParameters
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from diffusers_nodes_library.pipelines.flux.flux_pipeline_memory_footprint import clear_flux_pipeline
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class PipelineRunner(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.params = PipelineRunnerParameters(self)
        self.log_params = LogParameter(self)

        self.params.add_input_parameters()
        self.params.add_output_parameters()
        self.log_params.add_output_parameters()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self.params.after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        # Validate pipeline config hash exists
        config_hash = self.params.get_pipeline_config_hash()
        if not config_hash:
            errors.append(ValueError("Pipeline configuration is required. Connect a PipelineBuilder node."))
        elif config_hash not in model_cache._pipeline_cache:
            errors.append(
                ValueError(
                    f"Pipeline with config hash '{config_hash}' not found in cache. "
                    "Ensure the PipelineBuilder node has run successfully."
                )
            )

        # Validate prompt
        prompt = self.params.get_prompt()
        if not prompt or prompt.strip() == "":
            errors.append(ValueError("Prompt cannot be empty."))

        return errors if errors else None

    def preprocess(self) -> None:
        self.log_params.clear_logs()
        self.params.preprocess()

    async def aprocess(self) -> None:
        self.preprocess()
        self.log_params.append_to_logs("Starting pipeline execution...\\n")

        # Get pipeline configuration hash
        config_hash = self.params.get_pipeline_config_hash()
        self.log_params.append_to_logs(f"Using pipeline config: {config_hash}\\n")

        # Retrieve cached pipeline
        with self.log_params.append_profile_to_logs("Retrieving cached pipeline"):
            pipe = model_cache._pipeline_cache.get(config_hash)
            if pipe is None:
                error_msg = f"Pipeline with config hash '{config_hash}' not found in cache"
                self.log_params.append_to_logs(f"ERROR: {error_msg}\\n")
                raise RuntimeError(error_msg)

        # Set up preview placeholder
        self.params.publish_output_image_preview_placeholder()

        # Get pipeline parameters
        pipe_kwargs = self.params.get_pipe_kwargs()
        num_inference_steps = self.params.get_num_inference_steps()

        # Define callback for progress updates
        def callback_on_step_end(pipe_instance: Any, i: int, _t: Any, callback_kwargs: dict) -> dict:
            if i < num_inference_steps - 1:
                self.params.publish_output_image_preview_latents(pipe_instance, callback_kwargs["latents"])
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\\n")
            return {}

        # Execute pipeline with proper error handling
        try:
            with self.log_params.append_profile_to_logs("Pipeline inference"):
                self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\\n")

                # Execute the pipeline with progress callback
                result = await asyncio.to_thread(
                    pipe,
                    **pipe_kwargs,
                    output_type="pil",
                    callback_on_step_end=callback_on_step_end,
                )

                output_image_pil = result.images[0]

            # Publish final result
            self.params.publish_output_image(output_image_pil)
            self.log_params.append_to_logs("Generation complete.\\n")

        except Exception as e:
            error_msg = f"Pipeline execution failed: {e!s}"
            self.log_params.append_to_logs(f"ERROR: {error_msg}\\n")
            raise RuntimeError(error_msg) from e

        finally:
            # Clean up memory for Flux pipelines
            if isinstance(pipe, (diffusers.FluxPipeline, diffusers.FluxControlNetPipeline)):
                with self.log_params.append_profile_to_logs("Clearing memory"):
                    clear_flux_pipeline(pipe)

        self.log_params.append_to_logs("Pipeline execution complete.\\n")
