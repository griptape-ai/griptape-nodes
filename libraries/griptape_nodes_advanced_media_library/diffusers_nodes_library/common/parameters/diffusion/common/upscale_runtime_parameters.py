import logging
import math
from abc import ABC
from typing import Any

import PIL.Image
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image, Resampling
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)
from spandrel_nodes_library.utils import SpandrelPipeline  # type: ignore[reportMissingImports]
from utils.directory_utils import check_cleanup_intermediates_directory, get_intermediates_directory_path
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.misc.tiling_image_processor import (
    TilingImageProcessor,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DEFAULT_NUM_INFERENCE_STEPS,
    DiffusionPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.utils.math_utils import next_multiple_ge  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_file_parameter import (
    HuggingFaceRepoFileParameter,
)
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")

OUTPUT_SCALE = 4


class UpscalePipelineRuntimeParameters(DiffusionPipelineRuntimeParameters, ABC):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._refreshing_model_choices = False
        self._upscale_model_repo_parameter = HuggingFaceRepoFileParameter(
            self._node,
            repo_files=[
                ("Kim2091/ClearRealityV1", "4x-ClearRealityV1.pth"),
                ("Kim2091/UltraSharp", "4x-UltraSharp.pth"),
                ("Kim2091/UltraSharpV2", "4x-UltraSharpV2.pth"),
                ("Kim2091/AnimeSharp", "4x-AnimeSharp.pth"),
            ],
            deprecated_repo_files=[
                ("skbhadra/ClearRealityV1", "4x-ClearRealityV1.pth"),
                ("lokCX/4x-Ultrasharp", "4x-Ultrasharp.pth"),
            ],
            parameter_name="upscale_model",
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)

        # Prevent infinite recursion when refresh_parameters updates choices
        if self._refreshing_model_choices:
            return

        if parameter.name == "upscale_model":
            self._refreshing_model_choices = True
            try:
                # Pass the value being set so refresh can include it if deprecated
                self._upscale_model_repo_parameter.refresh_parameters(value_being_set=value)
            finally:
                self._refreshing_model_choices = False

    def _add_input_parameters(self) -> None:
        self._upscale_model_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Image to be used as the starting point.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="The prompt or prompts to guide the image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt_2",
                type="str",
                tooltip="The prompt or prompts to be sent to tokenizer_2 and text_encoder_2. If not defined, prompt is will be used instead",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                type="str",
                tooltip="The prompt or prompts not to guide the image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt_2",
                type="str",
                tooltip="The prompt or prompts not to guide the image generation to be sent to tokenizer_2 and text_encoder_2. If not defined, negative_prompt is used in all the text-encoders.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="upscaler_max_tile_size",
                default_value=256,
                type="int",
                tooltip="The maximum size (in pixels) of each tile during initial upscaling.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="upscaler_tile_overlap",
                default_value=16,
                type="int",
                tooltip="The amount of overlap (in pixels) between tiles during initial upscaling.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="upscaler_tile_strategy",
                default_value="linear",
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=[
                            "linear",
                            "chess",
                            "random",
                            "inward",
                            "outward",
                        ]
                    )
                },
                tooltip="The strategy to use during initial upscaling.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="scale",
                default_value=2,
                type="int",
                tooltip="The scale factor to use when resizing images.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="resample_strategy",
                default_value="lanczos",
                type="str",
                traits={
                    Options(
                        choices=[
                            "nearest",
                            "box",
                            "bilinear",
                            "hamming",
                            "bicubic",
                            "lanczos",
                        ]
                    )
                },
                tooltip="The resampling strategy to use when resizing images.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="diffuser_max_tile_size",
                default_value=1024,
                type="int",
                tooltip="The maximum size (in pixels) of each tile when processing images.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="diffuser_tile_overlap",
                default_value=64,
                type="int",
                tooltip="The amount of overlap (in pixels) between tiles when processing images.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="diffuser_tile_strategy",
                default_value="linear",
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=[
                            "linear",
                            "chess",
                            "random",
                            "inward",
                            "outward",
                        ]
                    )
                },
                tooltip="The strategy to use when processing image tiles.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="strength",
                default_value=0.3,
                type="float",
                tooltip="Indicates extent to transform the reference image.",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="true_cfg_scale",
                default_value=1.0,
                type="float",
                tooltip="True classifier-free guidance (guidance scale) is enabled when true_cfg_scale > 1 and negative_prompt is provided.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=3.5,
                type="float",
                tooltip="Higher guidance_scale encourages a model to generate images more aligned with prompt at the expense of lower image quality.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=DEFAULT_NUM_INFERENCE_STEPS,
                type="int",
                tooltip="The number of denoising steps. More denoising steps usually lead to a higher quality image at the expense of slower inference.",
            )
        )

        self._node.hide_parameter_by_name("prompt_2")
        self._node.hide_parameter_by_name("negative_prompt_2")

    def add_input_parameters(self) -> None:
        self._add_input_parameters()
        self._seed_parameter.add_input_parameters()

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("prompt_2")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("negative_prompt_2")
        self._node.remove_parameter_element_by_name("true_cfg_scale")
        self._node.remove_parameter_element_by_name("guidance_scale")
        self._node.remove_parameter_element_by_name("image")
        self._node.remove_parameter_element_by_name("strength")
        self._node.remove_parameter_element_by_name("upscaler_max_tile_size")
        self._node.remove_parameter_element_by_name("upscaler_tile_overlap")
        self._node.remove_parameter_element_by_name("upscaler_tile_strategy")
        self._node.remove_parameter_element_by_name("scale")
        self._node.remove_parameter_element_by_name("resample_strategy")
        self._node.remove_parameter_element_by_name("diffuser_max_tile_size")
        self._node.remove_parameter_element_by_name("diffuser_tile_overlap")
        self._node.remove_parameter_element_by_name("diffuser_tile_strategy")
        self._node.remove_parameter_element_by_name("num_inference_steps")

    def remove_input_parameters(self) -> None:
        self._seed_parameter.remove_input_parameters()
        self._upscale_model_repo_parameter.remove_input_parameters()
        self._remove_input_parameters()

    def get_image_pil(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("image")
        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        return input_image_pil.convert("RGB")

    def _get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "prompt_2": self._node.get_parameter_value("prompt_2"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "negative_prompt_2": self._node.get_parameter_value("negative_prompt_2"),
            "true_cfg_scale": self._node.get_parameter_value("true_cfg_scale"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "image": self.get_image_pil(),
            "strength": self._node.get_parameter_value("strength"),
        }
        if kwargs["prompt_2"] is None or kwargs["prompt_2"] == "":
            del kwargs["prompt_2"]
        if kwargs["negative_prompt_2"] is None or kwargs["negative_prompt_2"] == "":
            del kwargs["negative_prompt_2"]
        return kwargs

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._upscale_model_repo_parameter.validate_before_node_run()
        return errors or None

    def get_width(self) -> int:
        input_image_pil = self.get_image_pil()
        return input_image_pil.width

    def get_height(self) -> int:
        input_image_pil = self.get_image_pil()
        return input_image_pil.height

    def publish_output_image_preview_placeholder(self) -> None:
        input_image_pil = self.get_image_pil()
        width, height = input_image_pil.size

        # Check to ensure there's enough space in the intermediates directory
        # if that setting is enabled.
        check_cleanup_intermediates_directory()

        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter(
            "output_image",
            pil_to_image_artifact(preview_placeholder_image, directory_path=get_intermediates_directory_path()),
        )

    @property
    def upscaler_tile_size(self) -> int:
        upscaler_max_tile_size = int(self._node.get_parameter_value("upscaler_max_tile_size"))
        input_image_pil = self.get_image_pil()
        largest_reasonable_tile_width = next_multiple_ge(input_image_pil.width, 16)
        largest_reasonable_tile_height = next_multiple_ge(input_image_pil.height, 16)
        largest_reasonable_tile_size = max(largest_reasonable_tile_height, largest_reasonable_tile_width)
        tile_size = min(largest_reasonable_tile_size, upscaler_max_tile_size)

        if tile_size % 16 != 0:
            new_tile_size = next_multiple_ge(tile_size, 16)
            self._node.log_params.append_to_logs(  # type: ignore[reportAttributeAccessIssue]
                f"upscaler_max_tile_size({tile_size}) not multiple of 16, rounding up to {new_tile_size}.\n"
            )
            tile_size = new_tile_size
        return tile_size

    def _process_upscale(self, input_image_pil: Image) -> Image:
        upscaler_tile_overlap = self._node.get_parameter_value("upscaler_tile_overlap")
        upscaler_tile_strategy = self._node.get_parameter_value("upscaler_tile_strategy")

        with self._node.log_params.append_profile_to_logs("Loading model metadata"):  # type: ignore[reportAttributeAccessIssue]
            repo, revision = self._upscale_model_repo_parameter.get_repo_revision()
            filename = self._upscale_model_repo_parameter.get_repo_filename()
            pipe = SpandrelPipeline.from_hf_file(repo_id=repo, revision=revision, filename=filename)

        tiling_image_processor = TilingImageProcessor(
            pipe=pipe,
            tile_size=self.upscaler_tile_size,
            tile_overlap=upscaler_tile_overlap,
            tile_strategy=upscaler_tile_strategy,
        )
        num_tiles = tiling_image_processor.get_num_tiles(image=input_image_pil)

        def callback_on_tile_end(i: int, _preview_image_pil: Image) -> None:
            if i < num_tiles:
                self._node.log_params.append_to_logs(f"Finished tile {i} of {num_tiles}.\n")  # type: ignore[reportAttributeAccessIssue]
                self._node.log_params.append_to_logs(f"Starting tile {i + 1} of {num_tiles}...\n")  # type: ignore[reportAttributeAccessIssue]
                self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]

        self._node.log_params.append_to_logs(f"Starting tile 1 of {num_tiles}...\n")  # type: ignore[reportAttributeAccessIssue]
        self._node.progress_bar_component.initialize(num_tiles)  # type: ignore[reportAttributeAccessIssue]
        self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
        output_image_pil = tiling_image_processor.process(
            image=input_image_pil,
            output_scale=OUTPUT_SCALE,
            callback_on_tile_end=callback_on_tile_end,
        )
        self._node.log_params.append_to_logs(f"Finished tile {num_tiles} of {num_tiles}.\n")  # type: ignore[reportAttributeAccessIssue]
        return output_image_pil

    def _process_rescale(self, input_image_pil: Image) -> Image:
        scale = float(self._node.get_parameter_value("scale"))
        resample_strategy = str(self._node.get_parameter_value("resample_strategy"))

        resample = None
        match resample_strategy:
            case "nearest":
                resample = Resampling.NEAREST
            case "box":
                resample = Resampling.BOX
            case "bilinear":
                resample = Resampling.BILINEAR
            case "hamming":
                resample = Resampling.HAMMING
            case "bicubic":
                resample = Resampling.BICUBIC
            case "lanczos":
                resample = Resampling.LANCZOS
            case _:
                logger.exception("Unknown resampling strategy %s", resample_strategy)

        w, h = input_image_pil.size
        output_image_pil = input_image_pil.resize(
            size=(int(w * scale / OUTPUT_SCALE), int(h * scale / OUTPUT_SCALE)),
            resample=resample,
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/844
        )
        return output_image_pil

    def latents_to_image_pil(self, pipe: DiffusionPipeline, latents: Any) -> Image:
        tile_size = self.diffuser_tile_size
        latents = pipe._unpack_latents(latents, tile_size, tile_size, pipe.vae_scale_factor)
        latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
        image = pipe.vae.decode(latents, return_dict=False)[0]
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/845
        return pipe.image_processor.postprocess(image, output_type="pil")[0]

    @property
    def diffuser_tile_size(self) -> int:
        diffuser_max_tile_size = int(self._node.get_parameter_value("diffuser_max_tile_size"))
        input_image_pil = self.get_image_pil()
        largest_reasonable_tile_width = next_multiple_ge(input_image_pil.width, 16)
        largest_reasonable_tile_height = next_multiple_ge(input_image_pil.height, 16)
        largest_reasonable_tile_size = max(largest_reasonable_tile_height, largest_reasonable_tile_width)
        tile_size = min(largest_reasonable_tile_size, diffuser_max_tile_size)

        if tile_size % 16 != 0:
            new_tile_size = next_multiple_ge(tile_size, 16)
            self._node.log_params.append_to_logs(  # type: ignore[reportAttributeAccessIssue]
                f"diffuser_max_tile_size({tile_size}) not multiple of 16, rounding up to {new_tile_size}.\n"
            )
            tile_size = new_tile_size
        return tile_size

    def _process_img2img(self, pipe: DiffusionPipeline, input_image_pil: Image) -> Image:
        self.preprocess()
        diffuser_tile_overlap = int(self._node.get_parameter_value("diffuser_tile_overlap"))
        diffuser_tile_strategy = str(self._node.get_parameter_value("diffuser_tile_strategy"))
        strength = float(self._node.get_parameter_value("strength"))

        # Check to ensure there's enough space in the intermediates directory
        # if that setting is enabled.
        check_cleanup_intermediates_directory()

        if strength == 0:
            return input_image_pil

        num_inference_steps = self.get_num_inference_steps()
        strength_affected_steps = math.ceil(num_inference_steps * strength)

        def wrapped_pipe(tile: Image, _get_preview_image_with_partial_tile: Any) -> Image:
            def callback_on_step_end(_pipe: DiffusionPipeline, i: int, _t: Any, _callback_kwargs: dict) -> dict:
                # Check for cancellation request
                if self._node.is_cancellation_requested:
                    _pipe._interrupt = True
                    self._node.log_params.append_to_logs(  # type: ignore[reportAttributeAccessIssue]
                        "Cancellation requested, stopping after completing this step...\n"
                    )
                    return _callback_kwargs

                self._node.log_params.append_to_logs(  # type: ignore[reportAttributeAccessIssue]
                    f"Completed inference step {i + 1} of {strength_affected_steps}.\n"
                )
                return {}

            img2img_kwargs = self.get_pipe_kwargs()
            img2img_kwargs.pop("image")
            img2img_kwargs.pop("width")
            img2img_kwargs.pop("height")
            return (
                pipe(  # type: ignore[reportCallIssue]
                    **img2img_kwargs,
                    image=tile,
                    width=tile.width,
                    height=tile.height,
                    output_type="pil",
                    callback_on_step_end=callback_on_step_end,
                )
                .images[0]
                .convert("RGB")
            )

        tiling_image_processor = TilingImageProcessor(
            pipe=wrapped_pipe,
            tile_size=self.diffuser_tile_size,
            tile_overlap=diffuser_tile_overlap,
            tile_strategy=diffuser_tile_strategy,
        )
        num_tiles = tiling_image_processor.get_num_tiles(image=input_image_pil)

        def callback_on_tile_end(i: int, _preview_image_pil: Image) -> None:
            if i < num_tiles:
                # Check to ensure there's enough space in the intermediates directory
                # if that setting is enabled.
                check_cleanup_intermediates_directory()

                self._node.log_params.append_to_logs(f"Finished tile {i} of {num_tiles}.\n")  # type: ignore[reportAttributeAccessIssue]
                self._node.log_params.append_to_logs(f"Starting tile {i + 1} of {num_tiles}...\n")  # type: ignore[reportAttributeAccessIssue]

        self._node.log_params.append_to_logs(f"Starting tile 1 of {num_tiles}...\n")  # type: ignore[reportAttributeAccessIssue]
        output_image_pil = tiling_image_processor.process(
            image=input_image_pil,
            callback_on_tile_end=callback_on_tile_end,
        )
        self._node.log_params.append_to_logs(f"Finished tile {num_tiles} of {num_tiles}.\n")  # type: ignore[reportAttributeAccessIssue]
        return output_image_pil

    def process_pipeline(self, pipe: DiffusionPipeline) -> None:
        self._node.log_params.append_to_logs("Starting...\n")  # type: ignore[reportAttributeAccessIssue]
        input_image_pil = self.get_image_pil()
        upscaled_image_pil = self._process_upscale(input_image_pil)
        self._node.log_params.append_to_logs("Initial upscaling complete...\n")  # type: ignore[reportAttributeAccessIssue]
        rescaled_image_pil = self._process_rescale(upscaled_image_pil)
        self._node.log_params.append_to_logs("Rescaling complete...\n")  # type: ignore[reportAttributeAccessIssue]
        output_image_pil = self._process_img2img(pipe, rescaled_image_pil)

        self.publish_output_image(output_image_pil)
        self._node.log_params.append_to_logs("Done.\n")  # type: ignore[reportAttributeAccessIssue]
