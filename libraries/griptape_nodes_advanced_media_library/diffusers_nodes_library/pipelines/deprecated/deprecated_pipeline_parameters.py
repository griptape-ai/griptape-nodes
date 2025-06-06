import functools
from typing import Any

import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.file_path_parameter import FilePathParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.huggingface_model_parameter import HuggingfaceModelParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.option_utils import get_options_from_list  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import ControlNode


class DeprecatedPipelineParameters:
    def __init__(self, node: ControlNode):
        self.node = node

    def add_input_parameters(self) -> None:
        self.node.add_input_parameter(
            "pipeline_type",
            options=get_options_from_list([
                "alt_diffusion",
                "audio_diffusion", 
                "latent_diffusion_uncond",
                "pndm",
                "repaint",
                "score_sde_ve",
                "spectrogram_diffusion",
                "stable_diffusion_variants",
                "stochastic_karras_ve",
                "versatile_diffusion",
                "vq_diffusion"
            ]),
            default_value="alt_diffusion",
        )
        
        HuggingfaceModelParameter(self.node).add_input_parameters()
        SeedParameter(self.node).add_input_parameters()

        self.node.add_input_parameter("prompt", default_value="A beautiful landscape")
        self.node.add_input_parameter("negative_prompt", default_value="")
        self.node.add_input_parameter("num_inference_steps", default_value=20)
        self.node.add_input_parameter("guidance_scale", default_value=7.5)

    def add_output_parameters(self) -> None:
        self.node.add_output_parameter("output")

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        pass

    def validate_before_node_run(self) -> list[Exception]:
        errors = []
        return errors

    def preprocess(self) -> None:
        pass

    @functools.cache
    def get_pipeline_class(self):
        pipeline_type = self.node.get_input_parameter_value("pipeline_type")
        
        # Map pipeline types to their classes
        pipeline_mapping = {
            "alt_diffusion": diffusers.AltDiffusionPipeline,
            "audio_diffusion": diffusers.AudioDiffusionPipeline,
            "latent_diffusion_uncond": diffusers.LDMPipeline,
            "pndm": diffusers.PNDMPipeline,
            "repaint": diffusers.RePaintPipeline,
            "score_sde_ve": diffusers.ScoreSdeVePipeline,
            "spectrogram_diffusion": diffusers.SpectrogramDiffusionPipeline,
            "stable_diffusion_variants": diffusers.StableDiffusionPipeline,
            "stochastic_karras_ve": diffusers.KarrasVePipeline,
            "versatile_diffusion": diffusers.VersatileDiffusionPipeline,
            "vq_diffusion": diffusers.VQDiffusionPipeline
        }
        
        return pipeline_mapping.get(pipeline_type, diffusers.StableDiffusionPipeline)

    def get_repo_revision(self) -> tuple[str, str]:
        return HuggingfaceModelParameter(self.node).get_repo_revision()

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self.node.get_input_parameter_value("prompt"),
            "num_inference_steps": self.node.get_input_parameter_value("num_inference_steps"),
            "guidance_scale": self.node.get_input_parameter_value("guidance_scale"),
            "generator": SeedParameter(self.node).get_generator(),
        }

        negative_prompt = self.node.get_input_parameter_value("negative_prompt")
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def publish_output_preview_placeholder(self) -> None:
        pipeline_type = self.node.get_input_parameter_value("pipeline_type")
        self.node.set_output_parameter_value("output", f"Generating with {pipeline_type}...")

    def publish_output(self, output: Any) -> None:
        self.node.set_output_parameter_value("output", output)