import logging
import tempfile
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import numpy as np
import torch  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.wan.wan_image_to_video_pipeline_parameters import (
    WanImageToVideoPipelineParameters,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.wan.wan_loras_parameter import (
    WanLorasParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.wan.wan_pipeline_memory_footprint import (
    print_wan_pipeline_memory_footprint,
)  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class WanImageToVideoPipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = WanImageToVideoPipelineParameters(self)
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
        self.log_params.append_to_logs("Preparing models...\n")

        with (
            self.log_params.append_profile_to_logs("Loading model metadata"),
            self.log_params.append_logs_to_logs(logger=logger),
        ):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()

            image_encoder = model_cache.from_pretrained(
                transformers.CLIPVisionModel,  # type: ignore[reportAttributeAccessIssue]
                pretrained_model_name_or_path=base_repo_id,
                subfolder="image_encoder",
                torch_dtype=torch.float32,
            )

            vae = model_cache.from_pretrained(
                diffusers.AutoencoderKLWan,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                subfolder="vae",
                torch_dtype=torch.float32,
                local_files_only=True,
            )

            pipe = model_cache.from_pretrained(
                diffusers.WanImageToVideoPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
                vae=vae,
                image_encoder=image_encoder,
            )

            print_wan_pipeline_memory_footprint(pipe=pipe)

            logger.info("Moving to gpu")
            pipe.to("cuda")

        with (
            self.log_params.append_profile_to_logs("Configuring flux loras"),
            self.log_params.append_logs_to_logs(logger),
        ):
            self.loras_param.configure_loras(pipe)

        pipe_kwargs = self.pipe_params.get_pipe_kwargs()
        image = self.pipe_params.get_input_image_pil()
        # for 480
        max_area = 480 * 832
        # for 720
        max_area = 640 * 1024
        aspect_ratio = image.height / image.width
        mod_value = pipe.vae_scale_factor_spatial * pipe.transformer.config.patch_size[1]
        height = round(np.sqrt(max_area * aspect_ratio)) // mod_value * mod_value
        width = round(np.sqrt(max_area / aspect_ratio)) // mod_value * mod_value
        image = image.resize((width, height))
        pipe_kwargs["image"] = image
        pipe_kwargs["height"] = height
        pipe_kwargs["width"] = width

        with (
            self.log_params.append_profile_to_logs("Generating video"),
            self.log_params.append_logs_to_logs(logger=logger),
            self.log_params.append_stdout_to_logs(),
        ):
            frames = pipe(
                **pipe_kwargs,
            ).frames[0]

        with (
            self.log_params.append_profile_to_logs("Exporting to video"),
            self.log_params.append_logs_to_logs(logger=logger),
            self.log_params.append_stdout_to_logs(),
        ):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                temp_file = Path(tmp.name)
            try:
                diffusers.utils.export_to_video(frames, str(temp_file), fps=16)
                self.pipe_params.publish_output_video(temp_file)
            finally:
                if temp_file.exists():
                    temp_file.unlink()
