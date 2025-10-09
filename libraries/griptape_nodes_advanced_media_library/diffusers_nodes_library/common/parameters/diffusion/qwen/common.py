from typing import Any

import torch  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
from PIL.Image import Image


# Qwen uses special latents unpacking - https://github.com/huggingface/diffusers/blob/v0.35.1/src/diffusers/pipelines/qwenimage/pipeline_qwenimage.py#L708
def qwen_latents_to_image_pil(pipe: DiffusionPipeline, latents: Any, height: int, width: int) -> Image:
    """Convert the latents to a PIL image using Qwen specific logic."""
    latents = pipe._unpack_latents(latents, height, width, pipe.vae_scale_factor)
    latents_mean = (
        torch.tensor(pipe.vae.config.latents_mean)
        .view(1, pipe.vae.config.z_dim, 1, 1, 1)
        .to(latents.device, latents.dtype)
    )
    latents_std = 1.0 / torch.tensor(pipe.vae.config.latents_std).view(1, pipe.vae.config.z_dim, 1, 1, 1).to(
        latents.device, latents.dtype
    )
    latents = latents / latents_std + latents_mean
    image = pipe.vae.decode(latents, return_dict=False)[0][:, :, 0]
    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/845
    intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
    return intermediate_pil_image
