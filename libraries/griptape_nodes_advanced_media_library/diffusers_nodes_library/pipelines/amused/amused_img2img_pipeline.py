import logging
from typing import Any
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode

import diffusers  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.amused.amused_pipeline_parameters import AmusedPipelineParameters  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.amused.amused_memory_footprint import optimize_amused_pipeline_memory_footprint
from pillow_nodes_library.utils import image_artifact_to_pil  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.parameter_utils import LogParameter # type: ignore[reportMissingImports]

from diffusers_nodes_library.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedImg2ImgPipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "image"
        self.description = "Generates an image from text and an image using the flux.1 dev model"
        self.pipe_params = AmusedPipelineParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="input_image",
            )
        )
        self.add_parameter(
            Parameter(
                name="strength",
                default_value=0.5,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="strength",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
        )
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()
        

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.pipe_params.publish_output_image_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")
   
        with self.log_params.append_profile_to_logs("Loading flux model metadata"):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.AmusedImg2ImgPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading flux model"):
            with self.log_params.append_logs_to_logs(logger):
                optimize_amused_pipeline_memory_footprint(pipe)

        # with self.log_params.append_profile_to_logs("Configuring flux loras"):
        #     self.lora_params.configure_loras(pipe)

        num_inference_steps = self.pipe_params.get_num_inference_steps()
        def callback(i: int, _t: Any, latents: torch.Tensor) -> None:
            if i < num_inference_steps - 1:
                self.pipe_params.publish_output_image_preview_latents(pipe, latents)
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")

        # Width and height are determined by the input image...
        pipe_kwargs = self.pipe_params.get_pipe_kwargs()
        pipe_kwargs.pop("width")
        pipe_kwargs.pop("height")
        output_image_pil = pipe(
            **pipe_kwargs,
            image=self.get_input_image(),
            strength=self.get_strength(),
            output_type="pil",
            callback=callback,
        ).images[0]
        self.pipe_params.publish_output_image(output_image_pil)
        self.log_params.append_to_logs(f"Done.\n")


    def get_strength(self):
        return self.get_parameter_value("strength")

    def get_input_image(self):
        input_image_artifact = self.get_parameter_value("input_image")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")
        input_image_pil = input_image_pil.resize((512, 512))  # TODO: This is dumb for many reasons
        return input_image_pil