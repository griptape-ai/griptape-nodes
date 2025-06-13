import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


def print_animatediff_controlnet_pipeline_memory_footprint(
    pipe: diffusers.AnimateDiffControlNetPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Print memory footprint for core sub-modules of AnimateDiffControlNet pipelines."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vae",
            "text_encoder",
            "unet",
            "motion_adapter",
            "controlnet",
        ],
    )


@cache
def optimize_animatediff_controlnet_pipeline_memory_footprint(
    pipe: diffusers.AnimateDiffControlNetPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Apply optimizations to reduce memory usage.

    Raises:
        RuntimeError: If CUDA is not available.
    """
    if not torch.cuda.is_available():
        msg = "CUDA is not available"
        raise RuntimeError(msg)

    device = get_best_device()

    if device == torch.device("cuda"):
        logger.info("Enabling sequential CPU offload for CUDA device")
        pipe.enable_sequential_cpu_offload()
    else:
        logger.info("Moving pipeline to %s", device)
        pipe.to(device)

    logger.info("Enabling attention slicing and VAE slicing")
    pipe.enable_attention_slicing()
    if hasattr(pipe, "enable_vae_slicing"):
        pipe.enable_vae_slicing()
    elif hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
        pipe.vae.enable_slicing()  # type: ignore[attr-defined]

    logger.info("Final memory footprint:")
    print_animatediff_controlnet_pipeline_memory_footprint(pipe)
