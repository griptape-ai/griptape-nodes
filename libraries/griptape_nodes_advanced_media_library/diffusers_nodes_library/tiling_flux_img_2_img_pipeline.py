import contextlib
import logging
from collections.abc import Iterator
from typing import Any, ClassVar

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

from diffusers_nodes_library.utils.huggingface_utils import (  # type: ignore[reportMissingImports]
    list_repo_revisions_in_cache,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.utils.logging_utils import StdoutCapture  # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.lora_utils import configure_flux_loras  # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.math_utils import (  # type: ignore[reportMissingImports]
    next_multiple_ge,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.utils.tiling_image_processor import (  # type: ignore[reportMissingImports]
    TilingImageProcessor,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,  # type: ignore[reportMissingImports]
    optimize_flux_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class TilingFluxImg2ImgPipeline(ControlNode):
    _pipes: ClassVar[dict[str, diffusers.FluxImg2ImgPipeline]] = {}

    @classmethod
    def _get_pipe(cls, repo_id: str, revision: str) -> diffusers.FluxImg2ImgPipeline:
        key = TilingFluxImg2ImgPipeline._repo_revision_to_key((repo_id, revision))
        if key not in cls._pipes:
            if repo_id not in ("black-forest-labs/FLUX.1-dev", "black-forest-labs/FLUX.1-schnell"):
                logger.exception("Repo id %s not supported by %s", repo_id, cls.__name__)

            pipe = diffusers.FluxImg2ImgPipeline.from_pretrained(
                repo_id,
                revision=revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )
            optimize_flux_pipeline_memory_footprint(pipe)
            cls._pipes[key] = pipe

        return cls._pipes[key]

    @classmethod
    def _repo_revision_to_key(cls, repo_revision: tuple[str, str]) -> str:
        return f"{repo_revision[0]} ({repo_revision[1]})"

    @classmethod
    def _key_to_repo_revision(cls, key: str) -> tuple[str, str]:
        parts = key.rsplit(" (", maxsplit=1)
        if len(parts) != 2 or parts[1][-1] != ")":  # noqa: PLR2004
            logger.exception("Invalid key")
        return parts[0], parts[1][:-1]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "image/upscale"
        self.description = "Generates a new image given an image and text with tiling to support images of any size"

        self.repo_revisions = [
            *list_repo_revisions_in_cache("black-forest-labs/FLUX.1-schnell"),
            *list_repo_revisions_in_cache("black-forest-labs/FLUX.1-dev"),
        ]

        self.add_parameter(
            Parameter(
                name="model",
                default_value=(
                    TilingFluxImg2ImgPipeline._repo_revision_to_key(self.repo_revisions[0])
                    if self.repo_revisions
                    else None
                ),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(map(TilingFluxImg2ImgPipeline._repo_revision_to_key, self.repo_revisions)),
                    )
                },
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="model",
            )
        )
        self.add_parameter(
            Parameter(
                name="loras",
                input_types=["dict"],
                type="dict",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="loras",
            )
        )
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
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt_2",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional prompt_2 - defaults to prompt",
            )
        )
        self.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="negative_prompt",
            )
        )
        self.add_parameter(
            Parameter(
                name="negative_prompt_2",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional negative_prompt_2 - defaults to negative_prompt",
            )
        )
        self.add_parameter(
            Parameter(
                name="true_cfg_scale",
                default_value=1.0,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="true_cfg_scale",
            )
        )
        self.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=16,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_inference_steps",
            )
        )
        self.add_parameter(
            Parameter(
                name="strength",
                default_value=0.3,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="strength (basically denoise) -- 0.0 is original image 1.0 is a completely new image -- impacts effective steps",
            )
        )
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/841
        self.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=3.5,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="guidance_scale",
            )
        )
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/842
        self.add_parameter(
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional - random seed, default is random seed",
            )
        )
        self.add_parameter(
            Parameter(
                name="max_tile_size",
                default_value=1024,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip=(
                    "max_tile_size, "
                    "must be a multiple of 16, "
                    "if unecessily larger than input image, it will automatically "
                    "be lowered to smallest multiple of 16 that will fit the input image"
                ),
            )
        )
        self.add_parameter(
            Parameter(
                name="tile_overlap",
                default_value=64,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="tile_overlap",
            )
        )
        self.add_parameter(
            Parameter(
                name="tile_strategy",
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
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="tile_strategy",
            )
        )

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/843
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageUrlArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="logs",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="logs",
                ui_options={"multiline": True},
            )
        )

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:  # noqa: PLR0915, C901
        model = self.get_parameter_value("model")
        if model is None:
            logger.exception("No model specified")
        loras = self.get_parameter_value("loras")
        repo_id, revision = TilingFluxImg2ImgPipeline._key_to_repo_revision(model)
        input_image_artifact = self.get_parameter_value("input_image")
        prompt = self.get_parameter_value("prompt")
        prompt_2 = self.parameter_values.get("prompt_2", prompt)
        negative_prompt = self.get_parameter_value("negative_prompt")
        negative_prompt_2 = self.parameter_values.get("negative_prompt_2", prompt)
        true_cfg_scale = float(self.parameter_values["true_cfg_scale"])
        max_tile_size = int(self.get_parameter_value("max_tile_size"))
        tile_overlap = int(self.get_parameter_value("tile_overlap"))
        tile_strategy = str(self.get_parameter_value("tile_strategy"))
        num_inference_steps = int(self.parameter_values["num_inference_steps"])
        strength = float(self.get_parameter_value("strength"))
        guidance_scale = float(self.parameter_values["guidance_scale"])
        seed = int(self.parameter_values["seed"]) if ("seed" in self.parameter_values) else None

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")

        # The output image will be the same size as the input image.
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", input_image_pil.size, color="black")
        self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

        # Adjust tile size so that it is not much bigger than the input image.
        largest_reasonable_tile_width = next_multiple_ge(input_image_pil.width, 16)
        largest_reasonable_tile_height = next_multiple_ge(input_image_pil.height, 16)
        largest_reasonable_tile_size = max(largest_reasonable_tile_height, largest_reasonable_tile_width)
        tile_size = min(largest_reasonable_tile_size, max_tile_size)

        if tile_size % 16 != 0:
            new_tile_size = next_multiple_ge(tile_size, 16)
            self.append_value_to_parameter(
                "logs", f"max_tile_size({tile_size}) not multiple of 16, rounding up to {new_tile_size}.\n"
            )
            tile_size = new_tile_size

        if strength == 0:
            self.set_parameter_value("output_image", pil_to_image_artifact(input_image_pil))
            return

        seed = int(self.parameter_values["seed"]) if ("seed" in self.parameter_values) else None

        self.append_value_to_parameter("logs", "Preparing models...\n")
        with self._append_stdout_to_logs():
            pipe = self._get_pipe(repo_id, revision)

        configure_flux_loras(self, pipe, loras)

        def wrapped_pipe(tile: Image, get_preview_image_with_partial_tile: Any) -> Image:
            def callback_on_step_end(pipe: diffusers.FluxPipeline, i: int, _t: Any, callback_kwargs: dict) -> dict:
                if i < num_inference_steps - 1:
                    # Generate a preview image if this is not yet the last step.
                    # That would be redundant, since the pipeline automatically
                    # does that for the last step.
                    latents = callback_kwargs["latents"]
                    latents = pipe._unpack_latents(latents, tile_size, tile_size, pipe.vae_scale_factor)
                    latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
                    image = pipe.vae.decode(latents, return_dict=False)[0]
                    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/845
                    intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]

                    # HERE -> need to update the tile by calling something in the tile processor.
                    preview_image_with_partial_tile = get_preview_image_with_partial_tile(intermediate_pil_image)
                    self.publish_update_to_parameter(
                        "output_image", pil_to_image_artifact(preview_image_with_partial_tile)
                    )
                    self.append_value_to_parameter(
                        "logs", f"Finished inference step {i + 1} of {num_inference_steps}.\n"
                    )
                    self.append_value_to_parameter(
                        "logs", f"Starting inference step {i + 2} of {num_inference_steps}...\n"
                    )
                return {}

            return (
                pipe(
                    image=tile,
                    width=tile.width,
                    height=tile.height,
                    prompt=prompt,
                    prompt_2=prompt_2,
                    negative_prompt=negative_prompt,
                    negative_prompt_2=negative_prompt_2,
                    true_cfg_scale=true_cfg_scale,
                    strength=strength,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                    output_type="pil",
                    callback_on_step_end=callback_on_step_end,
                )
                .images[0]
                .convert("RGB")
            )

        tiling_image_processor = TilingImageProcessor(
            pipe=wrapped_pipe,
            tile_size=tile_size,
            tile_overlap=tile_overlap,
            tile_strategy=tile_strategy,
        )
        num_tiles = tiling_image_processor.get_num_tiles(image=input_image_pil)
        generator = torch.Generator(get_best_device())
        if seed is not None:
            generator = generator.manual_seed(seed)

        def callback_on_tile_end(i: int, preview_image_pil: Image) -> None:
            if i < num_tiles:
                self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_image_pil))
                self.append_value_to_parameter("logs", f"Finished tile {i} of {num_tiles}.\n")
                self.append_value_to_parameter("logs", f"Starting tile {i + 1} of {num_tiles}...\n")

        self.append_value_to_parameter("logs", f"Starting tile 1 of {num_tiles}...\n")
        output_image_pil = tiling_image_processor.process(
            image=input_image_pil,
            callback_on_tile_end=callback_on_tile_end,
        )
        self.append_value_to_parameter("logs", f"Finished tile {num_tiles} of {num_tiles}.\n")
        self.set_parameter_value("output_image", pil_to_image_artifact(output_image_pil))
        self.parameter_output_values["output_image"] = pil_to_image_artifact(output_image_pil)

    @contextlib.contextmanager
    def _append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self.append_value_to_parameter("logs", data)

        with StdoutCapture(callback):
            yield
