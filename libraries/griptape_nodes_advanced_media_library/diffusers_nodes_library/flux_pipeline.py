import contextlib
import logging
from collections.abc import Iterator
from typing import Any, ClassVar

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.utils.huggingface_utils import (  # type: ignore[reportMissingImports]
    list_repo_revisions_in_cache,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.utils.logging_utils import StdoutCapture  # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.lora_utils import configure_flux_loras  # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,  # type: ignore[reportMissingImports]
    optimize_flux_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class FluxPipeline(ControlNode):
    _pipes: ClassVar[dict[str, diffusers.FluxPipeline]] = {}

    @classmethod
    def _get_pipe(cls, repo_id: str, revision: str) -> diffusers.FluxPipeline:
        key = FluxPipeline._repo_revision_to_key((repo_id, revision))
        if key not in cls._pipes:
            if repo_id not in ("black-forest-labs/FLUX.1-dev", "black-forest-labs/FLUX.1-schnell"):
                logger.exception("Repo id %s not supported by %s", repo_id, cls.__name__)

            pipe = diffusers.FluxPipeline.from_pretrained(
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

        self.repo_revisions = [
            *list_repo_revisions_in_cache("black-forest-labs/FLUX.1-schnell"),
            *list_repo_revisions_in_cache("black-forest-labs/FLUX.1-dev"),
        ]

        self.category = "image"
        self.description = "Generates an image from text and an image using the flux.1 dev model"

        self.add_parameter(
            Parameter(
                name="model",
                default_value=(
                    FluxPipeline._repo_revision_to_key(self.repo_revisions[0]) if self.repo_revisions else None
                ),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(map(FluxPipeline._repo_revision_to_key, self.repo_revisions)),
                    )
                },
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
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
                tooltip="optional negative_prompt",
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
                name="width",
                default_value=1024,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="width",
            )
        )
        self.add_parameter(
            Parameter(
                name="height",
                default_value=1024,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="height",
            )
        )
        self.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=4,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_inference_steps",
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

    def _process(self) -> AsyncResult | None:
        model = self.get_parameter_value("model")
        if model is None:
            logger.exception("No model specified")
        loras = self.get_parameter_value("loras")
        repo_id, revision = FluxPipeline._key_to_repo_revision(model)
        prompt = self.parameter_values["prompt"]
        prompt_2 = self.parameter_values.get("prompt_2", prompt)
        negative_prompt = self.parameter_values["negative_prompt"]
        negative_prompt_2 = self.parameter_values.get("negative_prompt_2", negative_prompt)
        true_cfg_scale = float(self.parameter_values["true_cfg_scale"])
        width = int(self.parameter_values["width"])
        height = int(self.parameter_values["height"])
        num_inference_steps = int(self.parameter_values["num_inference_steps"])
        guidance_scale = float(self.parameter_values["guidance_scale"])
        seed = int(self.parameter_values["seed"]) if ("seed" in self.parameter_values) else None

        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

        self.append_value_to_parameter("logs", "Preparing models...\n")
        with self._append_stdout_to_logs():
            pipe = self._get_pipe(repo_id, revision)

        # Well, I guess it's ok to mutate the pipeline as long as we mutate it back
        # before another node instance uses it, since there is no parallelism.
        # Not sure if pytorch handles any model cachinging process -- that would be
        # nice since we don't want to duplicate such large objects (GBs) in RAM.

        configure_flux_loras(self, pipe, loras)

        generator = torch.Generator(get_best_device())
        if seed is not None:
            generator = generator.manual_seed(seed)

        def callback_on_step_end(pipe: diffusers.FluxPipeline, i: int, _t: Any, callback_kwargs: dict) -> dict:
            if i < num_inference_steps - 1:
                # Generate a preview image if this is not yet the last step.
                # That would be redundant, since the pipeline automatically
                # does that for the last step.
                latents = callback_kwargs["latents"]
                latents = pipe._unpack_latents(latents, height, width, pipe.vae_scale_factor)
                latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
                image = pipe.vae.decode(latents, return_dict=False)[0]
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/845
                intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
                self.publish_update_to_parameter("output_image", pil_to_image_artifact(intermediate_pil_image))
                self.append_value_to_parameter("logs", f"Finished inference step {i + 1} of {num_inference_steps}.\n")
                self.append_value_to_parameter("logs", f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}

        self.append_value_to_parameter("logs", f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = pipe(
            prompt=prompt,
            prompt_2=prompt_2,
            negative_prompt=negative_prompt,
            negative_prompt_2=negative_prompt_2,
            true_cfg_scale=true_cfg_scale,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            output_type="pil",
            generator=generator,
            callback_on_step_end=callback_on_step_end,
        ).images[0]
        self.set_parameter_value("output_image", pil_to_image_artifact(output_image_pil))
        self.parameter_output_values["output_image"] = pil_to_image_artifact(output_image_pil)
        self.append_value_to_parameter(
            "logs", f"Finished inference step {num_inference_steps} of {num_inference_steps}.\n"
        )

    @contextlib.contextmanager
    def _append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self.append_value_to_parameter("logs", data)

        with StdoutCapture(callback):
            yield
