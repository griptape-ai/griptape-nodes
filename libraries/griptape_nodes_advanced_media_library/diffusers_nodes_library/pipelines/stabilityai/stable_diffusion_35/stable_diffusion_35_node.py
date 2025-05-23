import logging
from typing import Any

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.stabilityai.stable_diffusion_35.helpers.sd35_model_manager import SD35ModelManager
from diffusers_nodes_library.pipelines.stabilityai.stable_diffusion_35.helpers.sd35_pipeline_parameters import SD35PipelineParameters
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusion35Pipeline(ControlNode):
    """Stable Diffusion 3.5 image generation node with dual mode support."""
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        
        # Initialize helper classes using Flux pattern
        self.model_manager = SD35ModelManager(self)
        self.pipe_params = SD35PipelineParameters(self)
        self.log_params = LogParameter(self)
        
        # Add parameters from helper classes
        self.model_manager.add_model_parameter()  # Add cached model selection
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()
    
    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        """Handle parameter value changes."""
        self.pipe_params.after_value_set(parameter, value, modified_parameters_set)
    
    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate node configuration before execution."""
        errors = []
        
        # Validate model availability
        model_errors = self.model_manager.validate_model_availability()
        if model_errors:
            errors.extend(model_errors)
        
        # Validate pipeline parameters
        param_errors = self.pipe_params.validate_before_node_run()
        if param_errors:
            errors.extend(param_errors)
        
        return errors or None
    
    def preprocess(self) -> None:
        """Preprocess parameters before execution."""
        self.pipe_params.preprocess()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
        
        # Publish preview placeholder immediately for UI responsiveness
        self.pipe_params.publish_output_image_preview_placeholder()
        
        with self.log_params.append_profile_to_logs("Loading model metadata"):
            pipe = self.model_manager.get_pipeline()
        
        # Get generation parameters
        pipe_kwargs = self.pipe_params.get_pipe_kwargs()
        
        # Setup progress callback
        num_inference_steps = self.pipe_params.get_num_inference_steps()
        
        def callback_on_step_end(pipe, step: int, _timestep, callback_kwargs) -> dict:
            if step < num_inference_steps - 1:
                self.log_params.append_to_logs(f"Inference step {step + 2} of {num_inference_steps}...\n")
            return {}
        
        # Run generation
        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        
        # Handle batch generation
        num_images = self.pipe_params.get_num_images_per_prompt()
        if num_images > 1:
            # Batch generation
            all_images = []
            for i in range(num_images):
                self.log_params.append_to_logs(f"Generating image {i + 1} of {num_images}...\n")
                result = pipe(
                    **pipe_kwargs,
                    num_images_per_prompt=1,
                    output_type="pil",
                    callback_on_step_end=callback_on_step_end,
                )
                all_images.extend(result.images)
            
            # Publish batch output
            self.pipe_params.publish_output_images_batch(all_images)
            
        else:
            # Single image generation
            result = pipe(
                **pipe_kwargs,
                output_type="pil", 
                callback_on_step_end=callback_on_step_end,
            )
            # Publish single output
            self.pipe_params.publish_output_image(result.images[0])
        
        self.log_params.append_to_logs("Generation complete.\n")
        
        return None 